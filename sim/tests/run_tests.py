#!/usr/bin/env python3
# Test driver for the MIPS-X simulator ('make check').
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Each tests/*.s file is assembled with mxasm.py into an ELF and run on
# the simulator.  Directives in comments at the top of the file:
#   ; ARGS: --hazards=warn       extra simulator options
#   ; RUNNER: --expect-exit=3    run through mipsx-run with these options
#   ; EXIT: 3                    expected exit status (default 0)
#   ; STDOUT: text               expected stdout, one line per directive
#                                (if absent, stdout must be empty)
#   ; STDERR: text               substring that must appear in stderr
#   ; NOT-STDERR: text           substring that must not appear in stderr
#   ; STDERR-EMPTY               stderr must be empty
#   ; STDIN: text                stdin contents (escapes allowed)
#   ; BASE: 0x0                  load address of the image (default 0x2000)
#   ; ELF: flags=0 machine=8 data=1 etype=1   ELF header overrides
import argparse
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxasm  # noqa: E402


def directives(text):
    d = {"ARGS": [], "RUNNER": None, "EXIT": 0, "STDOUT": None, "STDERR": [],
         "NOT-STDERR": [], "STDERR-EMPTY": False, "STDIN": "", "BASE": 0x2000,
         "ELF": {}}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith(";"):
            continue
        s = s[1:].strip()
        key, _, val = s.partition(":")
        key = key.strip()
        val = val[1:] if val.startswith(" ") else val
        if key == "ARGS":
            d["ARGS"] += val.split()
        elif key == "RUNNER":
            d["RUNNER"] = val.split()
        elif key == "EXIT":
            d["EXIT"] = int(val, 0)
        elif key == "STDOUT":
            d["STDOUT"] = (d["STDOUT"] or "") + val + "\n"
        elif key == "STDERR":
            d["STDERR"].append(val)
        elif key == "NOT-STDERR":
            d["NOT-STDERR"].append(val)
        elif s == "STDERR-EMPTY":
            d["STDERR-EMPTY"] = True
        elif key == "STDIN":
            d["STDIN"] += val.encode().decode("unicode_escape")
        elif key == "BASE":
            d["BASE"] = int(val, 0)
        elif key == "ELF":
            for kv in val.split():
                k, _, v = kv.partition("=")
                d["ELF"][k] = int(v, 0)
    return d


def run_one(path, args):
    name = os.path.basename(path)
    with open(path) as f:
        text = f.read()
    d = directives(text)
    elf = os.path.join(args.work, name[:-2] + ".elf")
    try:
        mxasm.assemble_file(text, elf, d["BASE"], **d["ELF"])
    except mxasm.AsmError as ex:
        return "assembly failed: %s" % ex
    if d["RUNNER"] is not None:
        cmd = ["sh", args.runner] + d["RUNNER"] + d["ARGS"] + [elf]
        env = dict(os.environ, MIPSX_SIM=os.path.abspath(args.sim))
    else:
        cmd = [args.sim] + d["ARGS"] + [elf]
        env = None
    try:
        p = subprocess.run(cmd, input=d["STDIN"].encode("latin-1"),
                           capture_output=True, timeout=60, env=env)
    except subprocess.TimeoutExpired:
        return "timed out"
    out = p.stdout.decode("latin-1")
    err = p.stderr.decode("utf-8", errors="replace")
    problems = []
    if p.returncode != d["EXIT"]:
        problems.append("exit status %d, expected %d" % (p.returncode, d["EXIT"]))
    if (d["STDOUT"] or "") != out:
        problems.append("stdout %r, expected %r" % (out, d["STDOUT"] or ""))
    for s in d["STDERR"]:
        if s not in err:
            problems.append("stderr lacks %r" % s)
    for s in d["NOT-STDERR"]:
        if s in err:
            problems.append("stderr contains %r" % s)
    if d["STDERR-EMPTY"] and err:
        problems.append("stderr not empty")
    if problems:
        return "; ".join(problems) + "\n  command: %s\n  stderr: %s" % (
            " ".join(cmd), err.strip().replace("\n", "\n          "))
    return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", required=True)
    ap.add_argument("--runner", required=True)
    ap.add_argument("--work", default="build/tests")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("tests", nargs="*")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    tests = args.tests or sorted(glob.glob(os.path.join(here, "*.s")))
    failed = 0
    for t in tests:
        res = run_one(t, args)
        if res:
            failed += 1
            print("FAIL %s: %s" % (os.path.basename(t), res))
        elif args.verbose:
            print("PASS %s" % os.path.basename(t))
    print("%d tests, %d passed, %d failed" % (len(tests), len(tests) - failed,
                                             failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
