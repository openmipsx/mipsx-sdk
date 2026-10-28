#!/usr/bin/env python3
"""mipsx-verify: checks an SPA3000 upgrade image against the format spec.

Copyright 2026 The mipsx-sdk authors.
SPDX-License-Identifier: Apache-2.0

Re-reads an image using only the rules of
linksys-spa3000/docs/spec/firmware-image-format.md ("spec"), independently
of mipsx_pack.py (it shares no code with it).  It applies every check the
spec says the boot selector or an installer makes, the structure the spec
describes for packed sections, and the extra rules for our own images
(only type 2 sections, open-source-stack.md §3.5).  Python 3 standard
library only.

Usage: mipsx_verify.py image.bin [-v] [--allow-types 0,1,2]
Exit status 0 if the image passes, 1 if not (each failure is printed).
"""

import argparse
import hashlib
import re
import struct
import sys
import zlib

MAGIC = b"SpA3000 FiRmWaRe"


class Report:
    def __init__(self):
        self.errors = []
        self.notes = []

    def check(self, ok, msg):
        if not ok:
            self.errors.append(msg)
        return ok


def u32(b, off):
    return struct.unpack_from(">I", b, off)[0]


def parse_version(field):
    """Returns the NUL-terminated ASCII string in FIELD, or None."""
    s = field.split(b"\0", 1)[0]
    if any(c < 0x20 or c > 0x7E for c in s):
        return None
    if field[len(s):].strip(b"\0"):
        return None                       # junk after the terminator
    return s.decode("ascii")


def version_acceptable(v):
    """Spec §5 (Installing, step 5): parsed as numbers; refused if
    unparseable, major 0, 1.0.x or 2.0.x."""
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        return False
    major, minor = int(m.group(1)), int(m.group(2))
    return not (major == 0 or (major in (1, 2) and minor == 0))


TAGS = {0: 0xC6F4B6AF, 1: 0xB8B4D4AD, 2: 0xCACAD3C3}   # spec §3


def check_entry(r, e, name):
    """Spec §3 and the boot selector's section check (§5, Section check)."""
    r.check(u32(e, 0x00) == 0, "%s: field 0x00 is not zero" % name)
    stype = e[0x08]
    r.check(stype in TAGS, "%s: unknown section type %d" % (name, stype))
    r.check(e[0x09:0x0C] == bytes(3), "%s: bytes 0x09-0x0B not zero" % name)
    if stype in TAGS:
        r.check(u32(e, 0x04) == TAGS[stype],
                "%s: tag 0x%08X does not match type %d" % (name, u32(e, 0x04),
                                                           stype))
    r.check(u32(e, 0x0C) == 0x80, "%s: data offset 0x%x, not 0x80"
            % (name, u32(e, 0x0C)))
    length = u32(e, 0x20)
    r.check(length <= 0xFFFFF, "%s: length 0x%x above 0xFFFFF" % (name, length))
    r.check(u32(e, 0x24) == 0, "%s: field 0x24 is not zero" % name)
    r.check(e[0x7C:0x7E] == b"\0\0", "%s: bytes 0x7C-0x7D not zero" % name)
    v = parse_version(e[0x28:0x7C])
    r.check(v is not None, "%s: version field is not a NUL-padded string"
            % name)
    r.check(struct.unpack_from(">H", e, 0x7E)[0] == sum(e[0:0x7E]) & 0xFFFF,
            "%s: byte sum at 0x7E is wrong" % name)
    # The boot selector's form of the same check.
    r.check(u32(e, 0x7C) == sum(e[0:0x7C]),
            "%s: word at 0x7C differs from the sum of bytes 0x00-0x7B" % name)
    return stype, length


def is_branch(word):
    """Spec processor §4 via abi §5.3: bits 31-30 = 00, condition one of
    eq, hs, lt, ne, lo, ge (1, 2, 3, 5, 6, 7)."""
    return word >> 30 == 0 and (word >> 27) & 7 in (1, 2, 3, 5, 6, 7)


def check_packed(r, data, name, ram_size):
    """Spec §4: packed sections (types 1 and 2).  Returns the RAM image the
    load directory describes, as {address: bytes}, and the entry byte
    address (or None)."""
    loads, entry = {}, None
    n = len(data)
    if not r.check(n >= 0x20 and n % 4 == 0,
                   "%s: length 0x%x is not a multiple of 4 of at least 0x20"
                   % (name, n)):
        return loads, entry
    (magic, dir_off, count, stack, length, enter, res0, res1) = \
        struct.unpack_from(">8I", data, 0)
    r.check(magic == 0x00060803, "%s: packed header 0x00 is 0x%08X, not "
            "0x00060803" % (name, magic))
    r.check(length == n, "%s: packed header length 0x%x, data is 0x%x"
            % (name, length, n))
    r.check(enter == n - 0x10, "%s: packed header 0x14 is not length - 0x10"
            % name)
    r.check(res0 == 0 and res1 == 0, "%s: packed header 0x18-0x1F not zero"
            % name)
    r.check(stack % 8 == 0 and 0 < stack <= ram_size,
            "%s: stack 0x%x is not an 8-aligned RAM address" % (name, stack))
    # The boot selector jumps to data + (length - 0x10) (§5, Order, 4); in
    # the stock sections that word is a branch back into the loader stub.
    if n >= 0x10:
        w = u32(data, n - 0x10)
        target = (n - 0x10) + 4 * (2 + ((w & 0xFFFF) ^ 0x8000) - 0x8000)
        r.check(is_branch(w) and 0x20 <= target < n,
                "%s: word at length - 0x10 is not a branch into the section"
                % name)
    # Chunks (§4.2).
    pos = 0x20
    while pos < n and data[pos] == 0x01:
        if not r.check(pos + 8 <= n, "%s: chunk header at 0x%x truncated"
                       % (name, pos)):
            return loads, entry
        clen = u32(data, pos + 4)
        r.check(data[pos + 2:pos + 4] == b"\0\0",
                "%s: chunk at 0x%x: bytes 2-3 not zero" % (name, pos))
        if not r.check(pos + 8 + clen <= n, "%s: chunk at 0x%x runs past the "
                       "section" % (name, pos)):
            return loads, entry
        pos += 8 + clen
    payload_start = pos
    # Directory (§4.4).
    if not r.check(dir_off % 4 == 0 and payload_start <= dir_off and
                   dir_off + 20 * count <= n - 0x10,
                   "%s: load directory (0x%x, %d records) is not inside the "
                   "section" % (name, dir_off, count)):
        return loads, entry
    ranges = []
    for i in range(count):
        rec = struct.unpack_from(">5I", data, dir_off + 20 * i)
        rtype, w1, w2, w3, w4 = rec
        what = "%s: record %d (type 0x%02x)" % (name, i, rtype)
        if rtype == 0x01:
            # Copy w3 words from header offset w1 to address w2 (§5, C).
            nbytes = 4 * w3
            if r.check(payload_start <= w1 and w1 % 4 == 0 and
                       w1 + nbytes <= dir_off,
                       "%s: source 0x%x+0x%x not between the chunks and the "
                       "directory" % (what, w1, nbytes)) and \
               r.check(w2 % 4 == 0 and w2 + nbytes <= ram_size,
                       "%s: destination 0x%x+0x%x not in RAM" % (what, w2,
                                                                  nbytes)):
                loads[w2] = data[w1:w1 + nbytes]
                ranges.append((w2, w2 + nbytes))
        elif rtype == 0x10:
            # Stream record (§4.3): pre[8], raw deflate, CRC-32 and length
            # (little-endian).
            if r.check(payload_start <= w1 < dir_off,
                       "%s: stream offset 0x%x outside the payload"
                       % (what, w1)):
                d = zlib.decompressobj(-15)
                try:
                    out = d.decompress(data[w1 + 8:dir_off])
                    ok = d.eof
                except zlib.error:
                    ok = False
                if r.check(ok, "%s: stream does not decompress" % what):
                    tail = d.unused_data
                    r.check(len(tail) >= 8 and
                            struct.unpack_from("<II", tail, 0) ==
                            (zlib.crc32(out), len(out)),
                            "%s: CRC-32 or length trailer wrong" % what)
                    r.check(w2 + len(out) <= ram_size,
                            "%s: destination not in RAM" % what)
                    loads[w2] = out
                    ranges.append((w2, w2 + len(out)))
        elif rtype == 0x02:
            pass      # zero-fill; its length unit is uncertain (§5, C)
        elif rtype in (0x05, 0x06, 0x07):
            pass      # register values, checked below
        elif rtype == 0x03:
            r.check(i == count - 1, "%s: entry record is not the last" % what)
            entry = (w1 & 0x3FFFFFFF) * 4
        else:
            r.check(False, "%s: unknown record type" % what)
    ranges.sort()
    for (a0, a1), (b0, b1) in zip(ranges, ranges[1:]):
        r.check(a1 <= b0, "%s: loads 0x%x-0x%x and 0x%x-0x%x overlap"
                % (name, a0, a1, b0, b1))
    if r.check(entry is not None, "%s: no entry record (type 0x03)" % name):
        r.check(any(a <= entry < b for a, b in ranges),
                "%s: entry 0x%x is not in loaded data" % (name, entry))
    # r23 rule (§4.4, Verified for section A): the 0x07 value is a loaded
    # range's word address + 0x10000.
    for i in range(count):
        rtype, w1 = struct.unpack_from(">II", data, dir_off + 20 * i)
        if rtype == 0x07:
            r.check(any(w1 == a // 4 + 0x10000 for a, _ in ranges),
                    "%s: r23 value 0x%x is not a loaded range's word address "
                    "+ 0x10000" % (name, w1))
    return loads, entry


def verify(image, allow_types=(2,), ram_size=0x200000):
    """Checks IMAGE (bytes).  Returns a Report with .errors (empty if the
    image passes), .loads ({address: bytes} for the type 2 section) and
    .entry."""
    r = Report()
    r.loads, r.entry = {}, None
    n = len(image)
    # Section B's checks (§5, Installing, steps 2-5) and the header (§2).
    if not r.check(n >= 0x200, "image shorter than its header and table "
                   "(0x200 bytes)"):
        return r
    r.check(image[0:16] == MAGIC, "bad magic")
    r.check(image[0x10:0x30] == bytes(0x20), "header 0x10-0x2F not zero")
    r.check(image[0x40:0x50] == bytes(0x10), "header 0x40-0x4F not zero")
    zeroed = image[:0x30] + bytes(16) + image[0x40:0x200]
    r.check(hashlib.md5(zeroed).digest() == image[0x30:0x40],
            "global header MD5 wrong")
    r.check(u32(image, 0x50) == 0x80 and u32(image, 0x54) == 0x80,
            "header fields 0x50/0x54 are not 0x80")
    r.check(u32(image, 0x58) == n, "header length 0x%x, file is 0x%x"
            % (u32(image, 0x58), n))
    v = parse_version(image[0x5C:0x7C])
    if r.check(v is not None, "image version is not a NUL-padded string"):
        r.check(version_acceptable(v),
                "image version %r would be refused by the installers" % v)
        r.version = v
    count = u32(image, 0x7C)
    if not r.check(1 <= count <= 3, "section count %d not 1-3" % count):
        return r
    # Table and sections (§1, §3).
    pos, total_app = 0x200, 0
    for i in range(3):
        e = image[0x80 + 0x80 * i:0x100 + 0x80 * i]
        name = "section %d" % i
        if i >= count:
            r.check(e == bytes(0x80), "table entry %d beyond the count is "
                    "not zero" % i)
            continue
        stype, length = check_entry(r, e, name)
        r.check(stype in allow_types, "%s has type %d; allowed: %s"
                % (name, stype, ", ".join(map(str, allow_types))))
        if not r.check(pos + 0x80 + length <= n, "%s runs past the end of "
                       "the file" % name):
            return r
        r.check(image[pos:pos + 0x80] == e,
                "%s: entry copy at 0x%x differs from the table" % (name, pos))
        data = image[pos + 0x80:pos + 0x80 + length]
        r.check(hashlib.md5(data).digest() == e[0x10:0x20],
                "%s: data MD5 wrong" % name)
        if stype in (1, 2):
            loads, entry = check_packed(r, data, name, ram_size)
            if stype == 2:
                r.loads, r.entry = loads, entry
                total_app += (0x80 + length + 0xFFFF) & ~0xFFFF
        pos += 0x80 + length
    r.check(pos == n, "sections end at 0x%x, file is 0x%x" % (pos, n))
    # Flash fit: type 2+ sections end at 0xF0000; the stock installer
    # rounds each to 64 KB; stock section B occupies 0x20000-0x40000 (§5).
    r.check(total_app <= 0xF0000 - 0x40000,
            "type 2 sections need 0x%x bytes of flash; 0x%x fit below "
            "0xF0000 above the recovery program" % (total_app, 0xB0000))
    return r


def main(argv=None):
    p = argparse.ArgumentParser(description="Verify an SPA3000 upgrade "
                                "image against the format spec.")
    p.add_argument("image")
    p.add_argument("--allow-types", default="2",
                   help="comma-separated section types to accept (default 2)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    with open(args.image, "rb") as f:
        image = f.read()
    r = verify(image, tuple(int(t) for t in args.allow_types.split(",")))
    for e in r.errors:
        print("mipsx-verify: %s: %s" % (args.image, e))
    if r.errors:
        return 1
    if args.verbose:
        print("%s: OK, version %s, entry 0x%x" % (args.image, r.version,
                                                  r.entry))
        for addr in sorted(r.loads):
            print("  load 0x%06x-0x%06x" % (addr, addr + len(r.loads[addr])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
