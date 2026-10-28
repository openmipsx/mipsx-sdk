#!/usr/bin/env python3
# Assemble a MIPS-X toolchain release archive.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
#   release/package.py --llvm-build ../llvm-project/build [--version V]
#
# Installs Clang, lld and the LLVM binary tools from an LLVM build of the
# fork (branch mipsx) with 'cmake --install --component', builds this
# SDK's run-time and picolibc with them into the toolchain's default
# sysroot (lib/clang-runtimes/mipsx), adds the simulator, the packer, the
# CMake and Meson files and the documentation, and writes
# <out>/mipsx-toolchain-<version>-<platform>.tar.xz and a .sha256 file.
# The SDK and picolibc are built from copies in the work directory, so
# their own build/ directories are left alone.
#
#   release/package.py --print-targets
#
# prints the ninja targets that the LLVM build needs (for CI).  The
# archive layout is described in release/TOOLCHAIN.md, which becomes the
# archive's README.md.

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile

SDK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ninja targets to build, and install components.  The symlink tools
# (llvm-ranlib, llvm-readelf, llvm-strip, llvm-addr2line, clang-cpp) come
# with their targets but are installed as components of their own.
TARGETS = [
    "clang", "lld", "clang-resource-headers", "llvm-mc", "llvm-objdump",
    "llvm-readobj", "llvm-ar", "llvm-nm", "llvm-objcopy", "llvm-size",
    "llvm-symbolizer", "llvm-dwarfdump", "llvm-cxxfilt",
]
COMPONENTS = TARGETS + [
    "clang-cpp", "llvm-ranlib", "llvm-readelf", "llvm-strip",
    "llvm-addr2line",
]

# Installed with clang and lld, but of no use for MIPS-X.
EXTRA_LINKS = ["clang-cl", "lld-link", "ld64.lld", "wasm-ld"]


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def git_rev(path, *args):
    try:
        return subprocess.run(
            ["git", "-C", path] + list(args), check=True,
            capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def describe(path):
    """'<git describe> <commit>', for BUILDINFO."""
    return "%s %s" % (
        git_rev(path, "describe", "--always", "--dirty", "--abbrev=12"),
        git_rev(path, "rev-parse", "HEAD"))


def host_platform():
    system = {"Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower())
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(
        platform.machine().lower(), platform.machine().lower())
    return "%s-%s" % (system, machine)


def copy_tree(src, dst):
    """Copy a source tree without its build output and git metadata."""
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", "build", "__pycache__", "*.o", "*.a"))


def install_llvm(build, stage, strip):
    for comp in COMPONENTS:
        cmd = ["cmake", "--install", build, "--prefix", stage,
               "--component", comp]
        if strip:
            cmd.append("--strip")
        run(cmd, stdout=subprocess.DEVNULL)
    # Drivers and linker flavours for other targets.
    for name in EXTRA_LINKS:
        path = os.path.join(stage, "bin", name)
        if os.path.lexists(path):
            os.remove(path)


def build_runtime(args, stage, work):
    sdk = os.path.join(work, "mipsx-sdk")
    copy_tree(SDK, sdk)
    bin_dir = os.path.join(stage, "bin")
    sysroot = os.path.join(stage, "lib", "clang-runtimes", "mipsx")
    make = [args.make, "-C", sdk, "MIPSX_LLVM_BIN=" + bin_dir,
            "SYSROOT=" + sysroot,
            "COMPILER_RT=" + os.path.join(args.llvm_src, "compiler-rt", "lib",
                                          "builtins")]
    run([args.make, "-C", sdk, "all"])
    if args.picolibc:
        pico = os.path.join(work, "picolibc")
        copy_tree(args.picolibc, pico)
        run(make + ["libc", "PICOLIBC_SRC=" + pico])
    else:
        run(make + ["sysroot"])
    return sdk


def install_sdk(args, sdk, stage):
    share = os.path.join(stage, "share", "mipsx-sdk")
    run([args.make, "-C", os.path.join(sdk, "sim"), "install",
         "PREFIX=" + stage])
    # The SDK's own layout under share/mipsx-sdk, so that cmake/mipsx.cmake
    # and meson/mipsx.txt find sim/mipsx-run, and mipsx-run finds the
    # simulator next to it.
    os.makedirs(os.path.join(share, "sim"))
    os.symlink("../../../bin/mipsx-run", os.path.join(share, "sim",
                                                      "mipsx-run"))
    os.symlink("../../../bin/mipsx-sim", os.path.join(share, "sim",
                                                      "mipsx-sim"))
    for d in ("cmake", "meson", "docs"):
        shutil.copytree(os.path.join(sdk, d), os.path.join(share, d))
    os.makedirs(os.path.join(share, "tools"))
    for f in ("mipsx_pack.py", "mipsx_verify.py", "loader-stub.s",
              "README.md"):
        shutil.copy2(os.path.join(sdk, "tools", f),
                     os.path.join(share, "tools", f))
    for f in ("mipsx-toolchain.cmake",):
        shutil.copy2(os.path.join(sdk, "release", f),
                     os.path.join(share, "cmake", f))
    shutil.copytree(os.path.join(sdk, "release", "examples"),
                    os.path.join(share, "examples"))
    for name, script in (("mipsx-pack", "mipsx_pack.py"),
                         ("mipsx-verify", "mipsx_verify.py")):
        path = os.path.join(stage, "bin", name)
        with open(path, "w") as f:
            f.write('#!/bin/sh\n'
                    '# Part of the MIPS-X toolchain release (mipsx-sdk).\n'
                    'dir=$(cd "$(dirname "$0")" && pwd)\n'
                    'exec python3 "$dir/../share/mipsx-sdk/tools/%s" "$@"\n'
                    % script)
        os.chmod(path, 0o755)


def write_docs(args, sdk, stage, version, plat):
    shutil.copy2(os.path.join(sdk, "release", "TOOLCHAIN.md"),
                 os.path.join(stage, "README.md"))
    lic = os.path.join(stage, "LICENSES")
    os.makedirs(lic)
    shutil.copy2(os.path.join(sdk, "LICENSE"),
                 os.path.join(lic, "mipsx-sdk.txt"))
    for proj in ("llvm", "clang", "lld", "compiler-rt"):
        shutil.copy2(os.path.join(args.llvm_src, proj, "LICENSE.TXT"),
                     os.path.join(lic, proj + ".txt"))
    if args.picolibc:
        shutil.copy2(os.path.join(args.picolibc, "COPYING.picolibc"),
                     os.path.join(lic, "picolibc.txt"))
    with open(os.path.join(stage, "BUILDINFO"), "w") as f:
        f.write("version: %s\nplatform: %s\n" % (version, plat))
        # name: git describe, then the full commit (CI checks out
        # compiler-rt and picolibc at these commits).
        f.write("llvm-project: %s\n" % describe(args.llvm_src))
        f.write("mipsx-sdk: %s\n" % describe(SDK))
        f.write("picolibc: %s\n" % (describe(args.picolibc)
                                    if args.picolibc else "none"))


def make_archive(stage, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".tar.xz")

    def norm(ti):
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        return ti

    # xz itself compresses on all cores; tarfile's lzma uses one.
    xz = shutil.which("xz")
    if xz:
        with open(path, "wb") as out:
            proc = subprocess.Popen([xz, "-T0", "-6", "-c"],
                                    stdin=subprocess.PIPE, stdout=out)
            with tarfile.open(fileobj=proc.stdin, mode="w|") as tar:
                tar.add(stage, arcname=name, filter=norm)
            proc.stdin.close()
            if proc.wait():
                sys.exit("xz failed")
    else:
        with tarfile.open(path, "w:xz", preset=6) as tar:
            tar.add(stage, arcname=name, filter=norm)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with open(path + ".sha256", "w") as f:
        f.write("%s  %s\n" % (h.hexdigest(), os.path.basename(path)))
    return path


def main():
    p = argparse.ArgumentParser(
        description="Assemble a MIPS-X toolchain release archive.")
    p.add_argument("--llvm-build", help="LLVM build directory of the fork")
    p.add_argument("--llvm-src",
                   help="llvm-project checkout (default: the build's source)")
    p.add_argument("--picolibc", default=os.path.join(SDK, "..", "picolibc"),
                   help="picolibc checkout, branch mipsx (default "
                        "../picolibc); 'none' for a sysroot without libc")
    p.add_argument("--version", default="dev")
    p.add_argument("--platform", default=host_platform())
    p.add_argument("--work", default=os.path.join(SDK, "build", "release"))
    p.add_argument("--out", default=os.path.join(SDK, "build", "dist"))
    p.add_argument("--no-strip", dest="strip", action="store_false")
    p.add_argument("--make", default=os.environ.get("MAKE", "make"))
    p.add_argument("--print-targets", action="store_true",
                   help="print the LLVM ninja targets needed and exit")
    args = p.parse_args()

    if args.print_targets:
        print(" ".join(TARGETS))
        return 0
    if not args.llvm_build:
        p.error("--llvm-build is required")
    args.llvm_build = os.path.abspath(args.llvm_build)
    if not args.llvm_src:
        with open(os.path.join(args.llvm_build, "CMakeCache.txt")) as f:
            for line in f:
                if line.startswith("LLVM_SOURCE_DIR:"):
                    args.llvm_src = os.path.dirname(
                        line.split("=", 1)[1].strip())
                    break
        if not args.llvm_src:
            p.error("--llvm-src is required")
    args.llvm_src = os.path.abspath(args.llvm_src)
    if args.picolibc == "none":
        args.picolibc = None
    elif args.picolibc:
        args.picolibc = os.path.abspath(args.picolibc)

    name = "mipsx-toolchain-%s-%s" % (args.version, args.platform)
    work = os.path.abspath(args.work)
    stage = os.path.join(work, name)
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)

    install_llvm(args.llvm_build, stage, args.strip)
    sdk = build_runtime(args, stage, work)
    install_sdk(args, sdk, stage)
    write_docs(args, sdk, stage, args.version, args.platform)
    path = make_archive(stage, os.path.abspath(args.out), name)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
