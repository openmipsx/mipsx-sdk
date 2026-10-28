#!/usr/bin/env python3
# Run C execution test suites on the MIPS-X simulator (tests/README.md).
# SPDX-License-Identifier: Apache-2.0
"""Compile, link and run C test programs with clang --target=mipsx.

Suites:
  builtins  compiler-rt/test/builtins/Unit/*_test.c
  torture   llvm-test-suite SingleSource/Regression/C/gcc-c-torture/execute

Each test ends in one of:
  PASS          exit status 0
  FAIL          non-zero exit status (abort() gives 134)
  HAZARD        the simulator stopped: pipeline hazard or other error (125)
  TIMEOUT       cycle limit (124) or wall-clock limit
  CRASH         the compiler crashed
  CERROR        the compiler reported an error
  LERROR        link error: an undefined __* runtime symbol, or other
  UNSUPPORTED   skipped by the suite's own lists, needs a header or a libc
                function that the test library does not have, or a
                feature the target lacks (__int128, x86, ...)
"""

import argparse
import collections
import concurrent.futures
import os
import shutil
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(HERE)
SUPPORT = os.path.join(HERE, "support")

# Built into lib/libbuiltins.a (see the top-level Makefile).
SDK_BUILTINS = set(
    """mulsi3 muldi3 divsi3 udivsi3 modsi3 umodsi3 divdi3 udivdi3 moddi3
    umoddi3 ashlsi3 ashldi3 lshrsi3 lshrdi3 ashrsi3 ashrdi3""".split())


def built_crt_sources():
    names = set(SDK_BUILTINS)
    with open(os.path.join(SDK, "Makefile")) as f:
        text = f.read()
    m = re.search(r"^CRT_SOURCES := (.*?)\n(?=\S)", text, re.M | re.S)
    names.update(m.group(1).replace("\\", " ").split())
    names.add("atomic")  # rt/atomic.c
    return names


class Runner:
    def __init__(self, args):
        self.args = args
        self.bin = args.llvm_bin
        self.clang = os.path.join(self.bin, "clang")
        self.sysroot = args.sysroot
        self.sim = args.sim
        self.has_libc = os.path.exists(
            os.path.join(self.sysroot, "lib", "libc.a"))
        if args.libc != "auto":
            if args.libc == "sysroot" and not self.has_libc:
                sys.exit("run_tests.py: no lib/libc.a in " + self.sysroot)
            self.has_libc = args.libc == "sysroot"
        self.tmp = tempfile.mkdtemp(prefix="mipsx-tests-")
        self.support_obj = None
        if not self.has_libc:
            self.support_obj = os.path.join(self.tmp, "minilibc.o")
            subprocess.run(self.base_cflags("-O2") + [
                "-fno-builtin", "-c",
                os.path.join(SUPPORT, "minilibc.c"), "-o", self.support_obj
            ], check=True)

    def base_cflags(self, opt):
        flags = [self.clang, "--target=mipsx", "--sysroot=" + self.sysroot,
                 opt]
        if not self.has_libc:
            flags += ["-isystem", os.path.join(SUPPORT, "include")]
        return flags

    def run_one(self, src, opt, extra_cflags):
        name = os.path.basename(src)
        exe = os.path.join(self.tmp, "%s%s.elf" % (name, opt))
        cmd = self.base_cflags(opt) + extra_cflags + self.args.cflags + [src]
        if self.support_obj:
            cmd += [self.support_obj, "-nolibc"]
        cmd += ["-o", exe]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=self.args.compile_timeout)
        except subprocess.TimeoutExpired:
            return "CRASH", "compile timeout"
        if p.returncode != 0:
            err = p.stderr
            if ("PLEASE submit a bug report" in err or p.returncode < 0
                    or "error in backend" in err):
                lines = [l for l in err.splitlines()
                         if "error" in l or "Assertion" in l or "LLVM ERROR" in l]
                return "CRASH", first(lines, err)
            m = re.search(r"fatal error: '([^']+)' file not found", err)
            if m:
                return "UNSUPPORTED", "header <%s>" % m.group(1)
            m = re.search(r"call to undeclared library function '(\w+)'", err)
            if m:
                return "UNSUPPORTED", "libc %s" % m.group(1)
            undef = re.findall(r"undefined symbol: (\S+)", err)
            if undef:
                rt = sorted({u for u in undef if u.startswith("__")})
                if rt:
                    return "LERROR", "undefined " + " ".join(rt)
                return "UNSUPPORTED", "libc " + " ".join(sorted(set(undef)))
            if "ld.lld" in err:
                return "LERROR", first([l for l in err.splitlines()
                                        if "error" in l], err)
            return "CERROR", first([l for l in err.splitlines()
                                    if "error:" in l], err)
        try:
            p = subprocess.run(
                [self.sim, "--max-cycles=%d" % self.args.max_cycles, exe],
                capture_output=True, text=True, timeout=self.args.run_timeout)
        except subprocess.TimeoutExpired:
            return "TIMEOUT", "wall clock"
        out = p.stdout + p.stderr
        if p.returncode == 0:
            if "skipped" in p.stdout.lower() and self.args.suite == "builtins":
                return "UNSUPPORTED", "test skipped itself"
            return "PASS", ""
        if p.returncode == 124:
            return "TIMEOUT", "cycle limit"
        if p.returncode == 125:
            m = re.search(r"mipsx-sim: error: (.*)", out)
            return "HAZARD", m.group(1) if m else out.strip()[-200:]
        return "FAIL", "exit %d %s" % (p.returncode,
                                       out.strip().replace("\n", " | ")[:200])


def first(lines, fallback):
    return (lines[0] if lines else fallback.strip()[:300]).strip()


# GCC torture: the suite's own skip lists and per-test flags.
TORTURE_SKIP_GROUPS = ["UnsupportedTests", "FailingTests", "MMapTests",
                       "X86OnlyTests", "MipsTestsToSkip", "Mips32TestsToSkip"]
CLANG_ERRORING_CFLAGS = {"-fno-early-inlining", "-fno-ira-share-spill-slots",
                         "-ftree-loop-distribution", "-fno-tree-bit-ccp",
                         "-fno-tree-coalesce-vars"}


def cmake_globs(path):
    groups = {}
    with open(path) as f:
        text = re.sub(r"#.*", "", f.read())
    for m in re.finditer(r"file\(GLOB (\w+) CONFIGURE_DEPENDS(.*?)\)", text,
                         re.S):
        groups.setdefault(m.group(1), set()).update(
            re.findall(r"[\w.+-]+\.c", m.group(2)))
    return groups


def dg_options(src):
    flags = []
    with open(src, errors="replace") as f:
        for line in f:
            m = re.search(r'dg-(additional-)?options ({ )?"([^"]*)"( })?(.*)',
                          line)
            if m and not re.search(r"{ +target", m.group(5)):
                flags += m.group(3).split()
    return [f for f in flags if f not in CLANG_ERRORING_CFLAGS]


# Tests that write and read back files (fopen, tmpnam): the simulator has
# no file system.
TORTURE_NEEDS_FILES = {"fprintf-2.c", "printf-2.c", "user-printf.c"}


def torture_tests(args):
    d = args.src
    groups = cmake_globs(os.path.join(d, "CMakeLists.txt"))
    skip = set()
    for g in TORTURE_SKIP_GROUPS:
        skip |= groups.get(g, set())
    for name in sorted(os.listdir(d)):
        if not name.endswith(".c"):
            continue
        src = os.path.join(d, name)
        if name in skip:
            yield src, None, "suite skip list"
            continue
        if name in TORTURE_NEEDS_FILES:
            yield src, None, "needs a file system"
            continue
        flags = ["-w", "-Wno-implicit-int", "-Wno-int-conversion",
                 "-Wno-implicit-function-declaration",
                 "-Wno-error=incompatible-pointer-types"]
        if name in groups.get("TestRequiresWNoReturnType", ()):
            flags.append("-Wno-return-type")
        if name in groups.get("TestRequiresFWrapV", ()):
            flags.append("-fwrapv")
        flags += dg_options(src)
        yield src, flags, None


STD_RUN = re.compile(r"^// RUN: %clang_builtins %s (-ffp-contract=off )?"
                     r"%librt( -lm)? -o %t && %run %t$")


def builtins_tests(args):
    d = args.src
    built = built_crt_sources()
    inc = os.path.join(args.compiler_rt, "lib", "builtins")
    for name in sorted(os.listdir(d)):
        if not name.endswith("_test.c"):
            continue
        src = os.path.join(d, name)
        with open(src, errors="replace") as f:
            head = [l.rstrip("\n") for l in f]
        reason = None
        runs = [l for l in head if l.startswith("// RUN:")]
        if len(runs) != 1 or not STD_RUN.match(runs[0]):
            reason = "non-standard RUN line"
        for l in head:
            m = re.match(r"// REQUIRES: (.*)", l)
            if m:
                for req in m.group(1).split(","):
                    req = req.strip()
                    r = re.match(r"librt_has_(\w+)$", req)
                    if req == "c99-complex" or (r and r.group(1) in built):
                        continue
                    if True:
                        reason = reason or "requires " + req
            m = re.match(r"// UNSUPPORTED: (.*)", l)
            if m and m.group(1).strip() == "true":
                reason = reason or "unsupported: true"
        # The function under test must be in our runtime.
        fn = re.sub(r"new$", "", name[:-len("_test.c")])
        if fn.startswith("compiler_rt_"):
            fn = None  # header-only helpers (int_math.h, fp_lib.h)
        if fn and fn not in built and reason is None and not args.all:
            reason = "%s not built" % fn
        flags = ["-I", inc, "-w"]
        if "-ffp-contract=off" in "".join(runs):
            flags.append("-ffp-contract=off")
        yield src, (None if reason else flags), reason


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("suite", choices=["builtins", "torture"])
    ap.add_argument("--llvm-bin", required=True)
    ap.add_argument("--src", help="test directory (default from the suite)")
    ap.add_argument("--compiler-rt",
                    help="compiler-rt directory (default <llvm-bin>/../../compiler-rt)")
    ap.add_argument("--sysroot", default=os.path.join(SDK, "build", "sysroot"))
    ap.add_argument("--sim", default=os.path.join(SDK, "sim", "build", "mipsx-sim"))
    ap.add_argument("-O", dest="opts", action="append",
                    help="optimisation level(s), e.g. -O 0 -O 2 (default both)")
    ap.add_argument("-j", type=int, default=os.cpu_count())
    ap.add_argument("--filter", help="only tests whose file name matches this regex")
    ap.add_argument("--max-cycles", type=int, default=1_000_000_000)
    ap.add_argument("--run-timeout", type=int, default=120)
    ap.add_argument("--compile-timeout", type=int, default=120)
    ap.add_argument("--libc", choices=["auto", "sysroot", "mini"],
                    default="auto",
                    help="C library: the sysroot's libc.a (picolibc), or the "
                    "small one in tests/support (default: libc.a if present)")
    ap.add_argument("--cflags", default="",
                    help="extra compiler flags for the tests (one string)")
    ap.add_argument("--results", help="write one line per test here")
    ap.add_argument("--keep", action="store_true", help="keep the executables")
    ap.add_argument("--all", action="store_true",
                    help="builtins: also run tests of functions not built")
    ap.add_argument("-v", action="store_true", help="print every non-PASS")
    args = ap.parse_args()

    args.cflags = args.cflags.split()
    args.compiler_rt = args.compiler_rt or os.path.join(
        args.llvm_bin, "..", "..", "compiler-rt")
    if not args.src:
        if args.suite == "builtins":
            args.src = os.path.join(args.compiler_rt, "test", "builtins", "Unit")
        else:
            args.src = os.path.join(SDK, "..", "llvm-test-suite", "SingleSource",
                                    "Regression", "C", "gcc-c-torture", "execute")
    opts = ["-O" + o for o in (args.opts or ["0", "2"])]

    runner = Runner(args)
    gen = builtins_tests if args.suite == "builtins" else torture_tests
    tests = [t for t in gen(args)
             if not args.filter or re.search(args.filter, os.path.basename(t[0]))]

    results = []
    with concurrent.futures.ThreadPoolExecutor(args.j) as pool:
        futs = {}
        for src, flags, reason in tests:
            for opt in opts:
                if flags is None:
                    results.append((os.path.basename(src), opt, "UNSUPPORTED", reason))
                else:
                    futs[pool.submit(runner.run_one, src, opt, flags)] = (src, opt)
        for fut in concurrent.futures.as_completed(futs):
            src, opt = futs[fut]
            status, detail = fut.result()
            results.append((os.path.basename(src), opt, status, detail))
    results.sort()
    if not args.keep:
        shutil.rmtree(runner.tmp, ignore_errors=True)

    if args.results:
        with open(args.results, "w") as f:
            for r in results:
                f.write("%s\t%s\t%s\t%s\n" % r)
    for opt in opts:
        rs = [r for r in results if r[1] == opt]
        c = collections.Counter(r[2] for r in rs)
        run = len(rs) - c["UNSUPPORTED"]
        print("%s %s: %d tests, %d unsupported, %d run: %d pass (%.1f%%)  %s" % (
            args.suite, opt, len(rs), c["UNSUPPORTED"], run, c["PASS"],
            100.0 * c["PASS"] / run if run else 0.0,
            " ".join("%s %d" % (k, v) for k, v in sorted(c.items())
                     if k not in ("PASS", "UNSUPPORTED"))))
    if args.v:
        for r in results:
            if r[2] not in ("PASS", "UNSUPPORTED"):
                print("%s %s %s %s" % r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
