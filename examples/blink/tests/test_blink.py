#!/usr/bin/env python3
# Tests for examples/blink: the packed images, the loader stub path on
# the simulator, and the start-up logic on the simulator with the
# peripheral model of sim/model.c.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Run with:  make check MIPSX_LLVM_BIN=... [SYSROOT=...]   (in examples/blink)
# or directly with BLINK_BUILD pointing at a directory holding blink.bin,
# blink-wd.bin and blink-sim.elf, and MIPSX_SIM at the simulator.  With
# neither BLINK_BUILD nor MIPSX_LLVM_BIN set the tests are skipped.

import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(EXAMPLE))
sys.path.insert(0, os.path.join(ROOT, "sim", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mxasm  # noqa: E402
import mipsx_verify as verify  # noqa: E402

SIM = os.environ.get("MIPSX_SIM",
                     os.path.join(ROOT, "sim", "build", "mipsx-sim"))
BUILD = os.environ.get("BLINK_BUILD")
LLVM_BIN = os.environ.get("MIPSX_LLVM_BIN")

START = 0x100     # first entry copy in a one-section image


def setUpModule():
    global BUILD, _tmp
    if BUILD:
        return
    if not LLVM_BIN:
        raise unittest.SkipTest("set BLINK_BUILD or MIPSX_LLVM_BIN")
    _tmp = tempfile.TemporaryDirectory()
    BUILD = _tmp.name
    cmd = ["make", "-C", EXAMPLE, "MIPSX_LLVM_BIN=" + LLVM_BIN,
           "O=" + BUILD, "all", "sim"]
    if os.environ.get("SYSROOT"):
        cmd.append("SYSROOT=" + os.environ["SYSROOT"])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def read(name):
    with open(os.path.join(BUILD, name), "rb") as f:
        return f.read()


class ImageTest(unittest.TestCase):
    def check_image(self, name):
        img = read(name)
        r = verify.verify(img)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.version, "9.0.1")
        self.assertEqual(struct.unpack_from(">I", img, 0x7C)[0], 1)
        self.assertEqual(img[0x88], 2)
        # The exception vector at 0 and the program at 0x2000 (rt/device.ld).
        self.assertIn(0, r.loads)
        self.assertEqual(len(r.loads[0]), 16)
        self.assertIn(0x2000, r.loads)
        self.assertEqual(r.entry, 0x2000)
        return img

    def test_blink(self):
        self.check_image("blink.bin")

    def test_blink_wd(self):
        self.check_image("blink-wd.bin")

    def test_variants_differ(self):
        # The two variants differ (the watchdog enable is compiled in).
        self.assertNotEqual(read("blink.bin"), read("blink-wd.bin"))


@unittest.skipUnless(os.path.exists(SIM), "simulator not built")
class StubTest(unittest.TestCase):
    """The packed image, started as the boot selector starts it (section
    in 'flash' above 4 MB, entered at data + length - 0x10), must get
    through the loader stub and crt0 into main.  The simulator has no
    peripherals, so the run must stop at main's first peripheral access:
    the interrupt-enable register 0x20004034 (peripherals.md §4, §7.2
    step 1), after the PSW has been written."""

    def run_at(self, name, flash_offset):
        sec = read(name)[START:]
        base = 0x400000 + flash_offset
        length, = struct.unpack_from(">I", sec, 0x20)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "flash.elf")
            mxasm.write_elf(path, base, sec, base + 0x80 + length - 0x10,
                            {"section_entry": base})
            p = subprocess.run([SIM, "--mem-size=0x800000", path],
                               capture_output=True, timeout=120)
        return p.returncode, p.stderr.decode()

    def test_placed_by_section_a(self):
        rc, err = self.run_at("blink.bin", 0x50000)
        self.assertEqual(rc, 125)
        self.assertIn("store to unmapped address 0x20004034", err)

    def test_placed_by_section_b(self):
        rc, err = self.run_at("blink-wd.bin", 0x557EC)
        self.assertEqual(rc, 125)
        self.assertIn("store to unmapped address 0x20004034", err)


@unittest.skipUnless(os.path.exists(SIM), "simulator not built")
class ModelTest(unittest.TestCase):
    """blink-sim.elf on the simulator with sim/model.c (ARM_SECONDS=3)."""

    def run_model(self, *opts):
        p = subprocess.run([SIM, os.path.join(BUILD, "blink-sim.elf")] +
                           list(opts), capture_output=True, timeout=600)
        out = p.stdout.decode()
        self.assertEqual(p.returncode, 0, out + p.stderr.decode())
        self.assertEqual(p.stderr.decode(), "")
        return out

    def led_times(self, out):
        return [int(m.group(1)) for m in
                re.finditer(r"\[t=(\d+)ms\] led: (on|off)", out)]

    def counts(self, out):
        m = re.search(r"model: erases (\d+) programs (\d+) kicks (\d+)", out)
        return tuple(int(x) for x in m.groups())

    def assert_period(self, out, ms):
        times = self.led_times(out)
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertGreaterEqual(len(gaps), 4, times)
        # Each toggle is one delay_ms(period) apart; the restore pauses
        # the LEDs once, so allow one long gap.
        long = [g for g in gaps[1:] if not ms <= g <= ms + 10]
        self.assertLessEqual(len(long), 1, gaps)

    def assert_net_done(self, out, seq_restored, seq_blank):
        self.assertIn("deadman: the slot loads this program; arming", out)
        self.assertIn("deadman: armed", out)
        self.assertIn("blink: healthy, restoring the boot record", out)
        self.assertIn("deadman: restored", out)
        self.assertIn("check: seq0 %d seq1 %d" % seq_restored, out)
        restored, blank = seq_blank
        # The area 0x400-0xFFFF of a rewritten block is a copy of the
        # active block's; where the two started out identical the model
        # reports it as unchanged.
        self.assertRegex(out, r"check: block %d area (as-at-start|"
                              r"copy-of-active), record slot-restored"
                              % restored)
        self.assertRegex(out, r"check: block %d area (as-at-start|"
                              r"copy-of-active), record slot-blank" % blank)
        erases, programs, kicks = self.counts(out)
        self.assertEqual(erases, 2)
        self.assertGreater(programs, 0x100)
        self.assertGreater(kicks, 10)

    def test_default(self):
        # Block 0 active (seq 5), block 1 older (seq 4): armed into block
        # 1 as seq 6, restored into block 0 as seq 7.
        out = self.run_model()
        self.assert_net_done(out, (7, 6), (0, 1))
        self.assert_period(out, 500)
        # First the LEDs are set off, then on, in the order data then
        # direction (peripherals.md §6).
        self.assertRegex(out, r"sysctl: reg 0x00000004 = 0x00000008\n"
                              r"\[t=1ms\] led: off\n"
                              r"\[t=1ms\] sysctl: reg 0x00000005 = 0x00000008")

    def test_block1_erased(self):
        out = self.run_model("--block1-erased")
        self.assert_net_done(out, (7, 6), (0, 1))

    def test_tie(self):
        # Equal sequence numbers: block 1 is taken as active, so the net
        # goes into block 0 first.
        out = self.run_model("--tie")
        self.assert_net_done(out, (6, 7), (1, 0))

    def test_stuck_timer(self):
        out = self.run_model("--stuck-timer")
        self.assertIn("timer: not counting, using a loop", out)
        self.assert_net_done(out, (7, 6), (0, 1))

    def assert_left_alone(self, out, reason, period):
        self.assertIn(reason, out)
        self.assertEqual(self.counts(out)[:2], (0, 0))
        self.assertIn("check: block 0 area as-at-start, record as-at-start",
                      out)
        self.assertIn("check: block 1 area as-at-start, record as-at-start",
                      out)
        self.assert_period(out, period)

    def test_no_record(self):
        out = self.run_model("--no-record")
        self.assert_left_alone(out, "deadman: no boot record", 1000)

    def test_slot_unused(self):
        out = self.run_model("--slot-unused")
        self.assert_left_alone(out, "deadman: type 2 slot unused", 1000)

    def test_not_ours(self):
        out = self.run_model("--not-ours")
        self.assert_left_alone(out, "that section is not this program", 1000)

    def test_bad_id(self):
        out = self.run_model("--bad-id")
        self.assert_left_alone(out, "deadman: flash not identified", 1000)

    def test_erase_fail(self):
        # DQ5 on every erase: three attempts, then the fast pattern, and
        # the active block untouched.
        out = self.run_model("--erase-fail")
        self.assertEqual(out.count("flash: erase attempt failed"), 3)
        self.assertIn("bootrec: erase failed", out)
        self.assertEqual(self.counts(out)[0], 3)
        self.assertIn("check: block 0 area as-at-start, record as-at-start",
                      out)
        self.assert_period(out, 125)

    def test_program_fail(self):
        out = self.run_model("--program-fail")
        self.assertIn("flash: program failed at", out)
        self.assertIn("bootrec: copy failed", out)
        self.assertIn("check: block 0 area as-at-start, record as-at-start",
                      out)
        self.assert_period(out, 125)


if __name__ == "__main__":
    unittest.main()
