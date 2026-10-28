#!/usr/bin/env python3
# Tests for the image packer and verifier (tools/).
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Run from the repository root:  python3 -m unittest discover -s tools/tests
# Programs are built with sim/tests/mxasm.py until the LLVM tools exist.
# No vendor bytes: every image here is made from our own test programs.

import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
sys.path.insert(0, os.path.join(ROOT, "sim", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mxasm  # noqa: E402
import mipsx_pack as pack  # noqa: E402
import mipsx_verify as verify  # noqa: E402

SIM = os.environ.get("MIPSX_SIM",
                     os.path.join(ROOT, "sim", "build", "mipsx-sim"))
RT = os.path.join(ROOT, "rt")


def read(path):
    with open(path) as f:
        return f.read()


def build_test_elf(path, **kw):
    """crt0 + exit-sim + rt/tests/crt0_main.s (prints, exits with 42)."""
    paths = [os.path.join(RT, "crt0.S"), os.path.join(RT, "exit-sim.S"),
             os.path.join(RT, "tests", "crt0_main.s")]
    asm = mxasm.link([read(p) for p in paths], path, names=paths, **kw)
    with open(path, "rb") as f:
        return f.read(), asm


def elf_segments(elf_bytes):
    """(paddr, file bytes) of each PT_LOAD with file data."""
    phoff, = struct.unpack_from(">I", elf_bytes, 28)
    phnum, = struct.unpack_from(">H", elf_bytes, 44)
    segs = []
    for i in range(phnum):
        t, off, _, paddr, filesz, _, _, _ = struct.unpack_from(
            ">8I", elf_bytes, phoff + 32 * i)
        if t == 1 and filesz:
            segs.append((paddr, elf_bytes[off:off + filesz]))
    return segs


def refresh(img):
    """Recomputes every checksum after a deliberate change, so that a test
    can reach the check behind them: section MD5, entry byte sum, entry
    copy and global MD5.  (A third implementation of the spec's rules.)"""
    img = bytearray(img)
    count, = struct.unpack_from(">I", img, 0x7C)
    pos = 0x200
    for i in range(min(count, 3)):
        e = 0x80 + 0x80 * i
        length, = struct.unpack_from(">I", img, e + 0x20)
        data = img[pos + 0x80:pos + 0x80 + length]
        img[e + 0x10:e + 0x20] = hashlib.md5(data).digest()
        struct.pack_into(">H", img, e + 0x7E, sum(img[e:e + 0x7E]) & 0xFFFF)
        img[pos:pos + 0x80] = img[e:e + 0x80]
        pos += 0x80 + length
    img[0x30:0x40] = bytes(16)
    img[0x30:0x40] = hashlib.md5(img[:0x200]).digest()
    return bytes(img)


DATA = 0x280      # section data offset in a one-section image


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.elf_path = os.path.join(cls.tmp.name, "prog.elf")
        cls.elf, cls.asm = build_test_elf(cls.elf_path)
        cls.image = pack.pack_elf(cls.elf, version="9.1.2(test)")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assertPasses(self, img, **kw):
        r = verify.verify(img, **kw)
        self.assertEqual(r.errors, [])
        return r

    def assertFails(self, img, text, **kw):
        r = verify.verify(img, **kw)
        self.assertTrue(any(text in e for e in r.errors),
                        "no error containing %r in %r" % (text, r.errors))


class StubTest(unittest.TestCase):
    def test_stub_words_match_source(self):
        asm = mxasm.Assembler(0)
        asm.parse(read(os.path.join(ROOT, "tools", "loader-stub.s")))
        img = asm.image()
        words = list(struct.unpack(">%dI" % (len(img) // 4), img))
        self.assertEqual(words, pack.STUB_WORDS)
        # Entry branch at length - 0x10, then two slots, then the length.
        self.assertEqual(words[-3:], [0x60000019, 0x60000019, 0])


class PackTest(Fixture):
    def test_verifies(self):
        r = self.assertPasses(self.image)
        self.assertEqual(r.version, "9.1.2(test)")

    def test_round_trip(self):
        # Applying the directory as the verifier reads it reproduces every
        # loaded byte of the ELF, and the entry point.
        r = self.assertPasses(self.image)
        want = {a: d + bytes(-len(d) % 4) for a, d in elf_segments(self.elf)}
        self.assertEqual(r.loads, want)
        self.assertEqual(r.entry, self.asm.labels["_start"])

    def test_layout_decisions(self):
        img = self.image
        self.assertEqual(img[:16], b"SpA3000 FiRmWaRe")
        self.assertEqual(struct.unpack_from(">I", img, 0x7C)[0], 1)
        self.assertEqual(img[0x88], 2)                      # type 2 only
        self.assertEqual(img[0x100:0x200], bytes(0x100))    # unused entries
        self.assertEqual(img[0x28 + 0x80:0x28 + 0x80 + 11], b"9.1.2(test)")
        length, = struct.unpack_from(">I", img, 0xA0)
        self.assertEqual(len(img), DATA + length)
        hdr = struct.unpack_from(">6I", img, DATA)
        self.assertEqual(hdr[0], 0x00060803)
        self.assertEqual(hdr[3], 0x1FFFF0)                  # __stack_top
        self.assertEqual(hdr[4:], (length, length - 0x10))
        # Last word of the section is its length; the empty chunk list.
        self.assertEqual(struct.unpack_from(">I", img, len(img) - 4)[0],
                         length)
        self.assertEqual(img[DATA + 0x20], 0)
        # Directory: copies, then r23, r24, entry (last, bit 30 set).
        dir_off, count = hdr[1], hdr[2]
        recs = [struct.unpack_from(">5I", img, DATA + dir_off + 20 * i)
                for i in range(count)]
        self.assertTrue(all(r[0] == 1 and r[4] == 1 for r in recs[:-3]))
        cb0 = self.asm.labels["__mipsx_cb0"]
        cb1 = self.asm.labels["__mipsx_cb1"]
        self.assertEqual(recs[-3], (7, cb0 >> 2, 0, 0, 0))
        self.assertEqual(recs[-2], (5, cb1 >> 2, 0, 0, 0))
        self.assertEqual(recs[-1], (3, 0x40000000 | (0x2000 >> 2), 0, 0, 0))

    def test_cli(self):
        out = os.path.join(self.tmp.name, "cli.bin")
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                         "mipsx_pack.py"),
                            self.elf_path, "-o", out, "--version",
                            "9.1.2(test)"], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), self.image)
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                         "mipsx_verify.py"),
                            "-v", out], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("OK", p.stdout)
        bad = os.path.join(self.tmp.name, "bad.bin")
        with open(bad, "wb") as f:
            f.write(self.image[:-1] + b"\x55")
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                         "mipsx_verify.py"),
                            bad], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("data MD5 wrong", p.stdout)


class PackErrorTest(Fixture):
    def elf_with(self, **kw):
        path = os.path.join(self.tmp.name, "e.elf")
        mxasm.write_elf(path, kw.pop("base", 0x2000), kw.pop("image", bytes(8)),
                        kw.pop("entry", 0x2000), {}, **kw)
        with open(path, "rb") as f:
            return f.read()

    def test_good_minimal(self):
        self.assertPasses(pack.pack_elf(self.elf_with()))

    def test_not_elf(self):
        with self.assertRaisesRegex(pack.PackError, "not an ELF"):
            pack.pack_elf(b"hello" * 20)

    def test_wrong_machine(self):
        with self.assertRaisesRegex(pack.PackError, "EM_MIPS_X"):
            pack.pack_elf(self.elf_with(machine=8))

    def test_little_endian(self):
        with self.assertRaisesRegex(pack.PackError, "big-endian"):
            pack.pack_elf(self.elf_with(data=1))

    def test_relocatable(self):
        with self.assertRaisesRegex(pack.PackError, "ET_EXEC"):
            pack.pack_elf(self.elf_with(etype=1))

    def test_reserved_flags(self):
        with self.assertRaisesRegex(pack.PackError, "e_flags"):
            pack.pack_elf(self.elf_with(flags=2))

    def test_entry_outside(self):
        with self.assertRaisesRegex(pack.PackError, "entry point"):
            pack.pack_elf(self.elf_with(entry=0x3000))

    def test_outside_ram(self):
        with self.assertRaisesRegex(pack.PackError, "outside RAM"):
            pack.pack_elf(self.elf_with(base=0x1FFFFC, entry=0x1FFFFC))

    def test_bad_versions(self):
        for v in ("0.9.1", "1.0.3", "2.0.0", "abc", "3.1", "3.1.20 GW"):
            with self.assertRaises(pack.PackError, msg=v):
                pack.pack_elf(self.elf, version=v)
        self.assertPasses(pack.pack_elf(self.elf, version="2.1.0"))
        with self.assertRaisesRegex(pack.PackError, "31 characters"):
            pack.pack_elf(self.elf, version="1.2.3(" + "x" * 30 + ")")

    def test_too_big_for_flash(self):
        # Fits the 0xFFFFF section limit but not beside the recovery
        # program (0xB0000 of flash for type 2 sections).
        img = bytes(0xB0000)
        with self.assertRaisesRegex(pack.PackError, "recovery program"):
            pack.pack_elf(self.elf_with(base=0x10000, entry=0x10000,
                                        image=img))
        self.assertPasses(pack.pack_elf(self.elf_with(
            base=0x10000, entry=0x10000, image=bytes(0x9F000))))

    def test_too_big_for_section(self):
        with self.assertRaisesRegex(pack.PackError, "0xfffff"):
            pack.pack_elf(self.elf_with(base=0x10000, entry=0x10000,
                                        image=bytes(0x100000)))


class CorruptImageTest(Fixture):
    """Each corruption must be rejected with the right message."""

    def mutate(self, offset, data, fix=True):
        img = bytearray(self.image)
        img[offset:offset + len(data)] = data
        return refresh(img) if fix else bytes(img)

    def word(self, offset, value, fix=True):
        return self.mutate(offset, struct.pack(">I", value), fix)

    def test_every_byte_flip_detected(self):
        # Every byte is covered by a checksum, a comparison or a field
        # check, so no single changed byte goes unnoticed.
        for off in range(len(self.image)):
            img = bytearray(self.image)
            img[off] ^= 0x10
            self.assertNotEqual(verify.verify(bytes(img)).errors, [],
                                "flip at 0x%x not detected" % off)

    def test_refresh_is_identity(self):
        self.assertEqual(refresh(self.image), self.image)

    def test_short(self):
        self.assertFails(self.image[:0x1F0], "shorter than its header")

    def test_magic(self):
        self.assertFails(self.mutate(0, b"SpA1001"), "bad magic")

    def test_global_md5(self):
        self.assertFails(self.mutate(0x60, b"8", fix=False),
                         "global header MD5 wrong")

    def test_reserved_header(self):
        self.assertFails(self.mutate(0x20, b"\x01"), "0x10-0x2F not zero")

    def test_header_sizes(self):
        self.assertFails(self.word(0x50, 0x100), "0x50/0x54")

    def test_truncated(self):
        self.assertFails(self.image[:-4], "header length")

    def test_appended(self):
        self.assertFails(self.image + bytes(4), "header length")

    def test_length_field(self):
        self.assertFails(self.word(0x58, len(self.image) + 4), "header length")

    def test_old_version(self):
        self.assertFails(self.mutate(0x5C, b"2.0.9(test)"), "refused")

    def test_version_not_string(self):
        self.assertFails(self.mutate(0x5C, b"9.\x01"), "not a NUL-padded")

    def test_count(self):
        self.assertFails(self.word(0x7C, 0), "count 0")
        self.assertFails(self.word(0x7C, 4), "count 4")

    def test_section_md5(self):
        self.assertFails(self.mutate(DATA + 0x30, b"\xFF", fix=False),
                         "data MD5 wrong")

    def test_entry_sum(self):
        img = bytearray(self.mutate(0x80 + 0x30, b"\x01"))
        img[0x80 + 0x7F] ^= 1                    # spoil only the sum
        img[0x200:0x280] = img[0x80:0x100]
        self.assertFails(refresh_global(img), "byte sum at 0x7E")

    def test_entry_copy(self):
        img = bytearray(self.image)
        img[0x200 + 0x40] ^= 0x20                # copy only, no refresh
        self.assertFails(bytes(img), "entry copy")

    def test_tag(self):
        self.assertFails(self.word(0x84, pack.TAGS[1]), "tag")

    def test_type_1(self):
        img = bytearray(self.image)
        img[0x88] = 1
        struct.pack_into(">I", img, 0x84, pack.TAGS[1])
        self.assertFails(refresh(img), "type 1; allowed: 2")
        self.assertPasses(refresh(img), allow_types=(1, 2))

    def test_unknown_type(self):
        self.assertFails(self.mutate(0x88, b"\x07"), "unknown section type")

    def test_entry_fields(self):
        self.assertFails(self.word(0x80, 1), "field 0x00")
        self.assertFails(self.word(0x8C, 0x100), "data offset")
        self.assertFails(self.word(0xA4, 1), "field 0x24")

    def test_entry_7c(self):
        self.assertFails(self.mutate(0xFC, b"x"), "0x7C-0x7D not zero")

    def test_section_too_long(self):
        self.assertFails(self.word(0xA0, 0x100000), "above 0xFFFFF")

    def test_section_length_past_eof(self):
        self.assertFails(self.word(0xA0, len(self.image)), "past the end")

    def test_unused_entry(self):
        self.assertFails(self.mutate(0x100, b"\x01"), "beyond the count")

    def test_packed_magic(self):
        self.assertFails(self.word(DATA, 0x00060804), "0x00060803")

    def test_packed_length(self):
        self.assertFails(self.word(DATA + 0x10, 0x1234), "packed header "
                         "length")
        self.assertFails(self.word(DATA + 0x14, 0x1234), "length - 0x10")

    def test_entry_word_not_branch(self):
        self.assertFails(self.word(len(self.image) - 0x10, 0x60000019),
                         "not a branch")

    def directory(self):
        dir_off, count = struct.unpack_from(">II", self.image, DATA + 4)
        return DATA + dir_off, count

    def test_directory_outside(self):
        self.assertFails(self.word(DATA + 4, 0x100000), "not inside")

    def test_no_entry_record(self):
        d, count = self.directory()
        self.assertFails(self.word(d + 20 * (count - 1), 0x06),
                         "no entry record")

    def test_entry_not_last(self):
        d, count = self.directory()
        img = bytearray(self.image)
        last = img[d + 20 * (count - 1):d + 20 * count]
        img[d + 20 * (count - 1):d + 20 * count] = img[d:d + 20]
        img[d:d + 20] = last
        self.assertFails(refresh(img), "not the last")

    def test_entry_outside_loads(self):
        d, count = self.directory()
        self.assertFails(self.word(d + 20 * (count - 1) + 4, 0x40100000),
                         "not in loaded data")

    def test_copy_outside_ram(self):
        d, _ = self.directory()
        self.assertFails(self.word(d + 8, 0x1FFFF0), "not in RAM")

    def test_copy_source_outside(self):
        d, _ = self.directory()
        self.assertFails(self.word(d + 4, 0x10), "not between")

    def test_overlapping_loads(self):
        d, _ = self.directory()
        second, = struct.unpack_from(">I", self.image, d + 20 + 8)
        self.assertFails(self.word(d + 8, second - 4), "overlap")

    def test_unknown_record(self):
        d, _ = self.directory()
        self.assertFails(self.word(d, 0x42), "unknown record type")

    def test_r23_rule(self):
        d, count = self.directory()
        self.assertFails(self.word(d + 20 * (count - 3) + 4, 0x12345),
                         "r23 value")


def refresh_global(img):
    img = bytearray(img)
    img[0x30:0x40] = bytes(16)
    img[0x30:0x40] = hashlib.md5(img[:0x200]).digest()
    return bytes(img)


class StreamRecordTest(unittest.TestCase):
    """The verifier also checks deflate stream records (format spec §4.3),
    which mipsx-pack does not write.  Built from our own bytes."""

    def section(self, payload, crc_delta=0):
        raw = zlib.compressobj(9, zlib.DEFLATED, -15)
        stream = raw.compress(payload) + raw.flush()
        rec = bytes(8) + stream + struct.pack("<II", (zlib.crc32(payload) +
                                                      crc_delta) & 0xFFFFFFFF,
                                              len(payload))
        rec += bytes(-len(rec) % 4)
        body = bytes(4) + rec                         # empty chunk list
        dir_off = 0x20 + len(body)
        dirs = struct.pack(">5I", 0x10, 0x24, 0x2000, 0, 1) + \
            struct.pack(">5I", 0x07, 0x2000 // 4 + 0x10000, 0, 0, 0) + \
            struct.pack(">5I", 0x03, 0x40000000 | 0x800, 0, 0, 0)
        tail = struct.pack(">4I", 0x0800FFFE, 0x60000019, 0x60000019, 0)
        n = dir_off + len(dirs) + len(tail)
        hdr = struct.pack(">6I8x", 0x00060803, dir_off, 3, 0x1FFFF0, n,
                          n - 0x10)
        data = bytearray(hdr + body + dirs + tail)
        struct.pack_into(">I", data, n - 4, n)
        return pack.build_image([(2, bytes(data), "9.0.0")], "9.0.0")

    def test_good_stream(self):
        payload = bytes(range(256)) * 16
        r = verify.verify(self.section(payload))
        self.assertEqual(r.errors, [])
        self.assertEqual(r.loads, {0x2000: payload})

    def test_bad_crc(self):
        r = verify.verify(self.section(b"abcd" * 100, crc_delta=1))
        self.assertTrue(any("CRC-32" in e for e in r.errors), r.errors)


@unittest.skipUnless(os.path.exists(SIM), "simulator not built")
class RunPackedTest(Fixture):
    """Runs the image's section on the simulator as the boot selector
    would start it: section entry and data placed in 'flash' (here RAM
    above 4 MB), entered at data + length - 0x10.  The loader stub must
    find itself, copy the program to 0x2000 and start crt0."""

    def run_at(self, flash_offset):
        sec = self.image[0x200:]
        base = 0x400000 + flash_offset
        length, = struct.unpack_from(">I", sec, 0x20)
        path = os.path.join(self.tmp.name, "flash.elf")
        mxasm.write_elf(path, base, sec, base + 0x80 + length - 0x10,
                        {"section_entry": base})
        p = subprocess.run([SIM, "--mem-size=0x800000", path],
                           capture_output=True, timeout=60)
        return p.returncode, p.stdout.decode(), p.stderr.decode()

    def test_placed_by_section_a(self):
        # Section A rounds sections to 64 KB, so they start on a sector.
        self.assertEqual(self.run_at(0x50000), (42, "hello, crt0\n", ""))

    def test_placed_by_section_b(self):
        # Section B packs to 4 bytes, so the start is anywhere.
        self.assertEqual(self.run_at(0x557EC), (42, "hello, crt0\n", ""))


if __name__ == "__main__":
    unittest.main()
