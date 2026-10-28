#!/usr/bin/env python3
# crt0 and the linker scripts built with the LLVM tools (llvm-mc, ld.lld).
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Assembles rt/ with llvm-mc, links with ld.lld and rt/sim.ld or
# rt/device.ld, and checks that:
#   - the layout and the abi §13.1 symbols match mxasm.link_layout(), which
#     the other rt/ tests use in place of the linker;
#   - the simulator build runs (crt0_main.s returns 42 with no hazards);
#   - the device build packs with tools/mipsx_pack.py and passes
#     tools/mipsx_verify.py;
#   - the helpers in rt/builtins assemble.
# Skipped unless $MIPSX_LLVM_BIN names a directory holding llvm-mc, ld.lld
# and llvm-readelf (for example llvm-project/build/bin).  Run from the
# repository root:
#     MIPSX_LLVM_BIN=... python3 -m unittest discover -s rt/tests

import glob
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
sys.path.insert(0, os.path.join(ROOT, "sim", "tests"))
import mxasm  # noqa: E402

SIM = os.environ.get("MIPSX_SIM",
                     os.path.join(ROOT, "sim", "build", "mipsx-sim"))
LLVM_BIN = os.environ.get("MIPSX_LLVM_BIN", "")
RT = os.path.join(ROOT, "rt")
TOOLS = os.path.join(ROOT, "tools")

# A small-data object, so that _gp is placed from .sdata and .sbss is used.
SMALL_DATA = """\
    .section .sdata,"aw",@progbits
    .word 7
    .section .sbss,"aw",@nobits
    .space 12
    .data
    .word 1, 2, 3
"""


def tool(name):
    return os.path.join(LLVM_BIN, name)


def run(*args):
    return subprocess.run(args, check=True, capture_output=True,
                          text=True).stdout


def readelf_layout(elf):
    """Returns ({section: (addr, size)}, {symbol: value}) from llvm-readelf."""
    secs, syms = {}, {}
    for line in run(tool("llvm-readelf"), "-S", "-W", elf).splitlines():
        p = line.replace("[ ", "[").split()
        if len(p) > 6 and p[0].startswith("[") and p[1].startswith("."):
            secs[p[1]] = (int(p[3], 16), int(p[5], 16))
    for line in run(tool("llvm-readelf"), "-s", "-W", elf).splitlines():
        p = line.split()
        if len(p) >= 8 and p[0].endswith(":") and p[0][:-1].isdigit():
            syms[p[7]] = int(p[1], 16)
    return secs, syms


@unittest.skipUnless(LLVM_BIN, "MIPSX_LLVM_BIN not set")
class LLVMLinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def assemble(self, src, name=None, text=None):
        if text is not None:
            src = self.path(name + ".s")
            with open(src, "w") as f:
                f.write(text)
        obj = self.path(os.path.basename(src) + ".o")
        run(tool("llvm-mc"), "-triple=mipsx", "-filetype=obj", src,
            "-o", obj)
        return obj

    def link(self, script, exit_file, extra=()):
        objs = [self.assemble(os.path.join(RT, "crt0.S")),
                self.assemble(os.path.join(RT, exit_file)),
                self.assemble(os.path.join(RT, "tests", "crt0_main.s"))]
        objs += list(extra)
        elf = self.path("prog.elf")
        run(tool("ld.lld"), "-T", os.path.join(RT, script), *objs,
            "-o", elf)
        return elf

    def check_layout(self, elf):
        secs, syms = readelf_layout(elf)
        sizes = {s: size for s, (_, size) in secs.items()}
        place, want = mxasm.link_layout(sizes)
        for s, (vma, _) in place.items():
            if sizes.get(s):
                self.assertEqual(secs[s][0], vma, "section " + s)
        for name, value in want.items():
            self.assertEqual(syms.get(name), value, name)

    def check_runs(self, elf):
        p = subprocess.run([SIM, elf], capture_output=True, timeout=60)
        self.assertEqual((p.returncode, p.stdout, p.stderr),
                         (42, b"hello, crt0\n", b""))

    @unittest.skipUnless(os.path.exists(SIM), "simulator not built")
    def test_sim(self):
        elf = self.link("sim.ld", "exit-sim.S")
        self.check_layout(elf)
        self.check_runs(elf)

    @unittest.skipUnless(os.path.exists(SIM), "simulator not built")
    def test_sim_small_data(self):
        small = self.assemble(None, "small", SMALL_DATA)
        elf = self.link("sim.ld", "exit-sim.S", [small])
        self.check_layout(elf)
        self.check_runs(elf)

    def test_sim_no_headers_in_load(self):
        # Nothing is free below 0x2000 at page alignment, so the ELF and
        # program headers must not be loaded (rt/README.md).
        elf = self.link("sim.ld", "exit-sim.S")
        out = run(tool("llvm-readelf"), "-l", "-W", elf)
        for line in out.splitlines():
            p = line.split()
            if p and p[0] == "LOAD":
                self.assertGreaterEqual(int(p[2], 16), 0x2000, line)

    def test_device_pack(self):
        elf = self.link("device.ld", "exit-device.S")
        self.check_layout(elf)
        image = self.path("prog.bin")
        run(sys.executable, os.path.join(TOOLS, "mipsx_pack.py"), elf,
            "-o", image, "--version", "9.0.0")
        out = run(sys.executable, os.path.join(TOOLS, "mipsx_verify.py"),
                  "-v", image)
        self.assertIn(": OK, version 9.0.0, entry 0x2000", out)

    def test_builtins_assemble(self):
        files = glob.glob(os.path.join(RT, "builtins", "*.S"))
        self.assertTrue(files)
        for src in files:
            with self.subTest(src=os.path.basename(src)):
                self.assemble(src)


if __name__ == "__main__":
    unittest.main()
