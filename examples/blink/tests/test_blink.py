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

    def selector(self, out):
        """The boot selector's view of the blocks, as the model reports
        it at the start and after every change (format spec §5)."""
        return re.findall(r"selector: (block \d type \d slot -> 0x\w+|scan)",
                          out)

    def assert_net_done(self, out, seq_restored, seq_blank):
        self.assertIn("deadman: the slot loads this program; arming", out)
        self.assertIn("deadman: armed", out)
        self.assertIn("blink: healthy, restoring the boot record", out)
        self.assertIn("deadman: restored", out)
        self.assertIn("check: seq0 %d seq1 %d" % seq_restored, out)
        restored, blank = seq_blank
        # The selector follows this program, then (armed) section B
        # through the type 1 slot of the new block, then this program
        # again from the restored block.
        self.assertEqual(self.selector(out), [
            "block %d type 2 slot -> 0x0c050000" % restored,
            "block %d type 1 slot -> 0x0c020000" % blank,
            "block %d type 2 slot -> 0x0c050000" % restored])
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
        # Equal sequence numbers: block 0 is active, as the boot selector
        # takes it (format spec §5; sections A and B would take block 1),
        # so the net goes into block 1 first.
        out = self.run_model("--tie")
        self.assert_net_done(out, (7, 6), (0, 1))

    def test_tie_block1_slotless(self):
        # A tie in which only block 0 has a type 2 slot: the selector
        # starts this program from block 0, so the net must arm.  (Taking
        # block 1 on a tie would find no slot and leave the net off.)
        out = self.run_model("--tie", "--block1-slotless")
        self.assert_net_done(out, (7, 6), (0, 1))

    def test_seq_unsigned(self):
        # Block 0 at 0x80000000 against block 1 at 4: newer only in an
        # unsigned compare, which is the selector's.
        out = self.run_model("--seq-high")
        self.assert_net_done(out, (0x80000002, 0x80000001), (0, 1))

    def test_odd_record(self):
        # The record found has a wrong complement and zeroed halfword
        # pairs, which the selector ignores.  The records written carry
        # the right complement and the installers' pairs (the model's
        # slot-blank and slot-restored checks require both).
        out = self.run_model("--odd-record")
        self.assert_net_done(out, (7, 6), (0, 1))

    def test_stuck_timer(self):
        out = self.run_model("--stuck-timer")
        self.assertIn("timer: not counting, using a loop", out)
        self.assert_net_done(out, (7, 6), (0, 1))

    def assert_code(self, out, n):
        """The skip code: bursts of N flashes (125 ms on, 125 ms off)
        separated by 1.5 s dark, at least two whole bursts."""
        events = re.findall(r"\[t=(\d+)ms\] led: (on|off)", out)
        ons = [int(t) for t, s in events if s == "on"]
        self.assertGreaterEqual(len(ons), 2 * n, events)
        bursts, cur = [], [ons[0]]
        for a, b in zip(ons, ons[1:]):
            if b - a > 1000:
                bursts.append(cur)
                cur = []
            cur.append(b)
        bursts.append(cur)
        self.assertGreaterEqual(len(bursts), 2, bursts)
        for burst in bursts[:-1]:
            self.assertEqual(len(burst), n, bursts)
            for a, b in zip(burst, burst[1:]):
                self.assertTrue(250 <= b - a <= 260, burst)
        for a, b in zip(bursts, bursts[1:]):
            self.assertGreaterEqual(b[0] - a[-1], 1500 + 125, bursts)
        # Every off after the first flash follows an on within 135 ms (the
        # off at start-up, before any flash, is stage 4's LEDs-off).
        for t, s in events:
            if s == "off" and int(t) > ons[0]:
                self.assertTrue(any(0 < int(t) - o <= 135 for o in ons),
                                events)

    def assert_left_alone(self, out, reason, code):
        self.assertIn(reason, out)
        self.assertEqual(self.counts(out)[:2], (0, 0))
        self.assertIn("check: block 0 area as-at-start, record as-at-start",
                      out)
        self.assertIn("check: block 1 area as-at-start, record as-at-start",
                      out)
        self.assert_code(out, code)

    def test_seq_wrap(self):
        # 0xFFFFFFFE leaves no room for seq + 1 and seq + 2 above it.
        out = self.run_model("--seq-wrap")
        self.assert_left_alone(out, "deadman: sequence number would wrap",
                               5)

    def test_block1_newer_slotless(self):
        # Block 1 is newer and has no type 2 slot: the selector follows it
        # (into section B), so whatever started this program, it was not
        # that record's slot.  Sections A and B would prefer block 0 for
        # its valid slot; the net must not.
        out = self.run_model("--block1-newer", "--block1-slotless")
        self.assertEqual(self.selector(out),
                         ["block 1 type 1 slot -> 0x0c020000"])
        self.assert_left_alone(out, "deadman: type 2 slot unused", 3)

    def test_no_record(self):
        out = self.run_model("--no-record")
        self.assert_left_alone(out, "deadman: no boot record", 2)

    def test_slot_unused(self):
        out = self.run_model("--slot-unused")
        self.assert_left_alone(out, "deadman: type 2 slot unused", 3)

    def test_not_ours(self):
        out = self.run_model("--not-ours")
        self.assert_left_alone(out, "that section is not this program", 4)

    def test_bad_id(self):
        out = self.run_model("--bad-id")
        self.assert_left_alone(out, "deadman: flash not identified", 1)

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
        # DQ5 on every program: 9 attempts at the first byte (section A's
        # count, flash.md §1), then the fast pattern.
        out = self.run_model("--program-fail")
        self.assertEqual(self.counts(out)[1], 9)
        self.assertIn("flash: program failed at", out)
        self.assertIn("bootrec: copy failed", out)
        self.assertIn("check: block 0 area as-at-start, record as-at-start",
                      out)
        self.assert_period(out, 125)


def board_supported():
    if not os.path.exists(SIM):
        return False
    p = subprocess.run([SIM, "--help"], capture_output=True)
    return b"--board" in p.stdout + p.stderr


@unittest.skipUnless(board_supported(), "simulator without --board")
class BoardTest(unittest.TestCase):
    """The device images on the simulator's SPA3000 board model
    (sim/README.md, "Board model"), which was written separately from
    sim/model.c.  The flash holds two boot records and the image's
    section at flash 0xE0000, where section A's installer puts it
    (tools/README.md); the run starts where the boot selector jumps,
    data start + packed header field 0x14 (format spec §5, "Order"
    step 4), and the code runs from flash."""

    SECTION = 0xE0000

    def record(self, seq, slot2=True):
        r = bytearray(b"\xff" * 0xA0)
        r[0:8] = b"SIPURA *"
        struct.pack_into(">II", r, 8, seq, seq ^ 0xFFFFFFFF)
        r[0x10:0x18] = bytes([4, 0, 0xFB, 0xFF, 0x10, 0, 0xEF, 0xFF])
        slots = [(0x20, 0x0C020000)]
        if slot2:
            slots.append((0x30, 0x0C000000 + self.SECTION))
        for off, addr in slots:
            r[off:off + 8] = b"SIPURA *"
            struct.pack_into(">II", r, off + 8, addr, addr ^ 0xFFFFFFFF)
        return r

    def run_board(self, name, seq0, seq1, seconds, *opts):
        sec = read(name)[START:]
        flash = bytearray(b"\xff" * 0x100000)
        flash[self.SECTION:self.SECTION + len(sec)] = sec
        flash[0:0xA0] = self.record(seq0)
        flash[0x10000:0x100A0] = self.record(seq1)
        field14, = struct.unpack_from(">I", sec, 0x80 + 0x14)
        entry = 0x0C000000 + self.SECTION + 0x80 + field14
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "flash.bin")
            epath = os.path.join(tmp, "start.elf")
            with open(fpath, "wb") as f:
                f.write(flash)
            # Nothing in RAM: an ELF whose entry is the flash address.
            mxasm.write_elf(epath, 0x1F0000, bytes(16), entry, {})
            p = subprocess.run([SIM, "--board=spa3000", "--flash=" + fpath,
                                "--max-cycles=%d" % int(seconds * 81e6)] +
                               list(opts) + [epath],
                               capture_output=True, timeout=600)
        log = p.stderr.decode()
        events = [(float(m.group(1)), m.group(2)) for m in re.finditer(
            r"^mipsx-sim: board: cycle \d+ \(([\d.]+) s\): (.*)$", log,
            re.M)]
        return p.returncode, log, events

    def leds(self, events):
        return [t for t, e in events if e.startswith("port0 led")]

    def erases(self, events):
        return [(t, e.split()[2]) for t, e in events
                if e.startswith("flash sector")]

    def test_tie_arms_from_block0(self):
        # Equal sequence numbers: the image must take block 0, as the
        # selector does, and so erase block 1 for the armed record.
        rc, log, events = self.run_board("blink.bin", 5, 5, 1.2)
        self.assertEqual(rc, 124, log)
        erases = self.erases(events)
        self.assertEqual([s for _, s in erases], ["0x10000"], log)
        leds = self.leds(events)
        self.assertGreater(leds[0], erases[0][0])
        gaps = [b - a for a, b in zip(leds[1:], leds[2:])]
        self.assertTrue(gaps and all(abs(g - 0.5) < 0.01 for g in gaps),
                        leds)

    def test_watchdog_variant_full_run(self):
        # blink-wd.bin with a 2 s watchdog: arms into block 1 before the
        # LEDs start, enables the watchdog, blinks at 0.5 s, restores
        # into block 0 at ARM_SECONDS (15 s) and keeps going, all without
        # a bite.
        rc, log, events = self.run_board("blink-wd.bin", 5, 4, 16.5,
                                         "--watchdog=2")
        # 124 is the cycle limit; a bite would be 123.
        self.assertEqual(rc, 124, log)
        enabled = [t for t, e in events if e.startswith("watchdog enabled")]
        self.assertEqual(len(enabled), 1, log)
        erases = self.erases(events)
        self.assertEqual([s for _, s in erases], ["0x10000", "0x00000"], log)
        leds = self.leds(events)
        self.assertGreater(leds[0], erases[0][0])
        self.assertGreater(enabled[0], erases[0][0])
        self.assertTrue(14.5 < erases[1][0] < 16.0, erases)
        before = [t for t in leds if t < erases[1][0]]
        gaps = [b - a for a, b in zip(before[1:], before[2:])]
        self.assertTrue(gaps and all(abs(g - 0.5) < 0.01 for g in gaps),
                        before)
        self.assertTrue(any(t > erases[1][0] + 0.5 for t in leds), leds)


if __name__ == "__main__":
    unittest.main()
