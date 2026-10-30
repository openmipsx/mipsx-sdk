#!/usr/bin/env python3
# Tests for crt0 (rt/crt0.S) on the simulator.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Until llvm-mc and lld support MIPS-X (work packages S3-S5), the programs
# are assembled and linked by sim/tests/mxasm.py, whose link_layout()
# mirrors rt/sim.ld.  Run from the repository root:
#     python3 -m unittest discover -s rt/tests
# $MIPSX_SIM overrides the simulator (default sim/build/mipsx-sim).

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
RT = os.path.join(ROOT, "rt")


def read(path):
    with open(path) as f:
        return f.read()


def link_program(out, main_src, board="sim", **kw):
    """crt0 + the board's exit and argument routines + MAIN_SRC (text),
    laid out like sim.ld."""
    paths = [os.path.join(RT, f)
             for f in ("crt0.S", "exit-%s.S" % board, "args-%s.S" % board)]
    texts = [read(p) for p in paths] + [main_src]
    return mxasm.link(texts, out, names=paths + ["main"], **kw)


def run_sim(elf, *opts):
    p = subprocess.run([SIM] + list(opts) + [elf], capture_output=True,
                       timeout=60)
    return p.returncode, p.stdout.decode("latin-1"), \
        p.stderr.decode("utf-8", "replace")


MAIN = read(os.path.join(RT, "tests", "crt0_main.s"))


@unittest.skipUnless(os.path.exists(SIM), "simulator not built")
class Crt0Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.elf = os.path.join(self.tmp.name, "prog.elf")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, src=MAIN, **kw):
        link_program(self.elf, src, **kw)
        return run_sim(self.elf)

    def test_hello(self):
        # crt0_main.s checks the registers, .data, .bss and the
        # constructor, prints and returns 42; any hazard fails (status 125).
        status, out, err = self.run_main()
        self.assertEqual((status, out, err), (42, "hello, crt0\n", ""))

    def test_bss_cleared(self):
        # The ELF loads 0xAA over .bss; crt0 must clear it.
        status, out, err = self.run_main(bss_fill=0xAA)
        self.assertEqual((status, out, err), (42, "hello, crt0\n", ""))

    def test_data_copied(self):
        # .data runs at 0x180000 but is loaded after .init_array.
        status, out, err = self.run_main(data_vma=0x180000, bss_fill=0x55)
        self.assertEqual((status, out, err), (42, "hello, crt0\n", ""))

    def test_args(self):
        # The simulator's command line reaches main: print argv[1..] and
        # return argc.  argv[0] is the ELF's path as given.
        src = """
    .text
main:
    mov     r4,r6               ; argc, kept for the result
    addi    r5,#4,r7            ; &argv[1]
1:
    ld      0[r7],r8
    addi    r7,#4,r7
    beq     r8,r0,3f            ; argv[argc] is null
    nop
    nop
2:
    ldbu    0[r8],r9
    addi    r8,#1,r8
    beq     r9,r0,4f
    nop
    nop
    stb     -65536[r0],r9       ; putchar
    b       2b
    nop
    nop
4:
    addi    r0,#10,r9
    stb     -65536[r0],r9
    b       1b
    nop
    nop
3:
    mov     r6,r2
    ret
    nop
    nop
"""
        link_program(self.elf, src)
        status, out, err = run_sim(self.elf)
        self.assertEqual((status, out, err), (1, "", ""))
        p = subprocess.run([SIM, self.elf, "hello", "", "wörld", "--stats"],
                           capture_output=True, timeout=60)
        self.assertEqual((p.returncode, p.stdout, p.stderr),
                         (5, "hello\n\nwörld\n--stats\n".encode(), b""))
        # mipsx-run splits --args at blanks, without globbing, and puts
        # the words after the ELF (picolibc passes them after it).
        p = subprocess.run(["sh", os.path.join(ROOT, "sim", "mipsx-run"),
                            self.elf, "--args", " hello  * world "],
                           capture_output=True, timeout=60,
                           env=dict(os.environ, MIPSX_SIM=SIM))
        self.assertEqual((p.returncode, p.stdout, p.stderr),
                         (4, b"hello\n*\nworld\n", b""))

    def test_exit_status_truncated(self):
        # main's result goes to exit; the simulator keeps the low 8 bits.
        src = """
    .text
main:
    li      #0x1234503,r2
    ret
    nop
    nop
"""
        status, out, err = self.run_main(src)
        self.assertEqual((status, out, err), (3, "", ""))

    def test_layout_symbols(self):
        # The symbols of abi §13.1, as link_layout (sim.ld) defines them.
        asm = link_program(self.elf, MAIN)
        s = asm.labels
        self.assertEqual(s["_start"], 0x2000)
        self.assertEqual(s["__text_start"], 0x2000)
        self.assertEqual(s["__mipsx_cb0"], 0x42000)
        self.assertEqual(s["__mipsx_cb1"], 0xC2000)
        self.assertEqual(s["__stack_top"], 0x1FFFF0)
        self.assertEqual(s["_gp"], s["__data_start"] + 0x10000)
        self.assertEqual(s["__data_load"], s["__data_start"])
        for name in ("__data_start", "__data_end", "__bss_start",
                     "__bss_end", "__init_array_start", "__init_array_end"):
            self.assertEqual(s[name] % 4, 0, name)
        self.assertEqual(s["__init_array_end"] - s["__init_array_start"], 4)
        self.assertLessEqual(s["__data_end"], s["__bss_start"])

    def test_device_exit_stops(self):
        # exit-device.S loops; the simulator's cycle limit stops it.
        link_program(self.elf, MAIN, board="device")
        status, out, err = run_sim(self.elf, "--max-cycles=100000")
        self.assertEqual((status, out), (124, "hello, crt0\n"))


if __name__ == "__main__":
    unittest.main()
