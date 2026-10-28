#!/usr/bin/env python3
"""mipsx-pack: turns a linked MIPS-X ELF executable into an SPA3000
upgrade image.

Copyright 2026 The mipsx-sdk authors.
SPDX-License-Identifier: Apache-2.0

Written from openmipsx/devices common/firmware-image-format.md ("format
spec") alone, with no vendor code or data.  Python 3 standard library
only.  The image holds one section, of type 2 (application), so that a
stock installer leaves the boot section and the recovery program alone
(openmipsx/.github plan/open-source-stack.md §3.5).  See tools/README.md for the layout and the
decisions behind it.

Usage: mipsx_pack.py prog.elf -o prog.bin [--version 9.0.0]
"""

import argparse
import hashlib
import re
import struct
import sys

IMAGE_MAGIC = b"SpA3000 FiRmWaRe"             # format spec §2
TAGS = {0: 0xC6F4B6AF, 1: 0xB8B4D4AD, 2: 0xCACAD3C3}   # §3, field 0x04
PACKED_MAGIC = 0x00060803                      # §4.1, field 0x00
HEADER_SIZE = 0x80                             # global header and entries
TABLE_ENTRIES = 3                              # §1: table at 0x080-0x1FF
SECTIONS_START = 0x200
MAX_SECTION_LENGTH = 0xFFFFF                   # §3, field 0x20
# Type 2 sections end at flash offset 0xF0000 (§5, flash layout).  Stock
# section B sits at 0x20000 and fills its sector to 0x40000; the stock
# application's installer rounds each section up to 64 KB.  So everything
# of type 2 must fit in 0xF0000 - 0x40000 once rounded up.
APP_FLASH_SPACE = 0xF0000 - 0x40000
RAM_SIZE = 0x200000                            # 2 MB SDRAM at 0
DEFAULT_STACK = 0x001FFFF0                     # §4.1 field 0x0C, abi §13.2

# Load directory record types (§4.4, §5 Section C).
REC_COPY, REC_ENTRY, REC_CB1, REC_CB0 = 0x01, 0x03, 0x05, 0x07
ENTRY_FLAG = 0x40000000                        # bit 30, as in stock images

# tools/loader-stub.s, assembled (base 0).  The last word is the section
# length, filled in by pack_section().  tools/tests checks these against
# the source.
STUB_WORDS = [
    0xE005FF1F, 0x48042254, 0xE006C000, 0x48063238, 0xE0C60019, 0x90041FF0,
    0x90061FF4, 0x90061FF8, 0xC03E07FC, 0x60000019, 0x60000019, 0x483EA204,
    0xE2940104, 0x8297FFFC, 0x60000019, 0x6296A066, 0x82980004, 0x829A0008,
    0x6298C019, 0x0B400030, 0x60000019, 0x60000019, 0x831C0000, 0x831E0004,
    0x83200008, 0x8322000C, 0xE3180014, 0xE35BFFFF, 0xE0040001, 0x0B840011,
    0x60000019, 0x60000019, 0xE0040003, 0x0B84001C, 0x60000019, 0x60000019,
    0xE0040007, 0x2B840002, 0x60000019, 0x60000019, 0x63C17019, 0xE0040005,
    0x2B84FFE7, 0x60000019, 0x60000019, 0x0800FFE4, 0x63C18019, 0x60000019,
    0x629EF019, 0x0C40FFE0, 0x60000019, 0x60000019, 0x83C40000, 0xE3DE0004,
    0xE463FFFF, 0x94040000, 0xE4200004, 0x2C40FFF9, 0x60000019, 0x60000019,
    0x0800FFD5, 0x60000019, 0x60000019, 0x481EF204, 0x4BC0F274, 0x62804019,
    0xC3C00000, 0x60000019, 0x60000019, 0x0800FFFE, 0x60000019, 0x60000019,
    0x0800FFB6, 0x60000019, 0x60000019, 0x00000000,
]

# ELF constants (abi §11).
EM_MIPS_X = 51
ET_EXEC = 2
PT_LOAD = 1
SHT_SYMTAB = 2
EF_MIPSX_ES3890 = 1


class PackError(Exception):
    pass


# --- ELF input -------------------------------------------------------------

class Elf:
    """The parts of an ET_EXEC that the packer needs."""

    def __init__(self, data):
        if len(data) < 52 or data[:4] != b"\x7fELF":
            raise PackError("not an ELF file")
        if data[4] != 1 or data[5] != 2:
            raise PackError("not a 32-bit big-endian ELF file")
        (etype, machine, _, self.entry, phoff, shoff, self.flags, _, phentsize,
         phnum, shentsize, shnum, _) = struct.unpack_from(">HHIIIIIHHHHHH",
                                                          data, 16)
        if machine != EM_MIPS_X:
            raise PackError("e_machine is %d, not EM_MIPS_X (51)" % machine)
        if etype != ET_EXEC:
            raise PackError("not an executable (ET_EXEC); link it first")
        if self.flags & ~EF_MIPSX_ES3890:
            raise PackError("unsupported e_flags 0x%x (abi §11.2)" % self.flags)
        self.segments = []      # (load address, bytes, memsz)
        for i in range(phnum):
            off = phoff + i * phentsize
            if off + 32 > len(data):
                raise PackError("program header %d outside the file" % i)
            (ptype, poff, vaddr, paddr, filesz, memsz, _, _) = \
                struct.unpack_from(">IIIIIIII", data, off)
            if ptype != PT_LOAD or memsz == 0:
                continue
            if poff + filesz > len(data):
                raise PackError("segment %d outside the file" % i)
            self.segments.append((paddr, data[poff:poff + filesz], memsz))
        self.symbols = {}
        for i in range(shnum):
            off = shoff + i * shentsize
            if off + 40 > len(data):
                break
            (_, shtype, _, _, soff, size, link, _, _, entsize) = \
                struct.unpack_from(">IIIIIIIIII", data, off)
            if shtype != SHT_SYMTAB or entsize != 16:
                continue
            stroff = struct.unpack_from(">I", data, shoff + link * shentsize + 16)[0]
            for j in range(size // 16):
                name, value = struct.unpack_from(">II", data, soff + j * 16)
                end = data.index(b"\0", stroff + name)
                self.symbols[data[stroff + name:end].decode("latin-1")] = value


# --- Image output ----------------------------------------------------------

def check_version(version, what):
    """The installers parse the version as numbers and refuse major 0,
    1.0.x and 2.0.x (format spec §5, Installing, step 5)."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(\([\x20-\x7E]*\))?", version)
    if not m:
        raise PackError("%s %r is not of the form N.N.N or N.N.N(text)"
                        % (what, version))
    major, minor = int(m.group(1)), int(m.group(2))
    if major == 0 or (major in (1, 2) and minor == 0):
        raise PackError("%s %r would be refused (major 0, 1.0.x and 2.0.x "
                        "are; format spec §5)" % (what, version))


def plan_segments(elf):
    """Checks the ELF's loadable segments and returns (address, bytes)
    pairs, padded to words.  The tail of a segment beyond its file size
    (.bss) is not stored: crt0 clears .bss (abi §13.3)."""
    segs = []
    for paddr, data, memsz in sorted(elf.segments):
        if paddr % 4:
            raise PackError("segment at 0x%x is not word aligned" % paddr)
        if paddr + memsz > RAM_SIZE:
            raise PackError("segment 0x%x-0x%x is outside RAM (0-0x%x)"
                            % (paddr, paddr + memsz, RAM_SIZE))
        if data:
            segs.append((paddr, data + bytes(-len(data) % 4)))
    for (a, d), (b, _) in zip(segs, segs[1:]):
        if a + len(d) > b:
            raise PackError("segments at 0x%x and 0x%x overlap" % (a, b))
    if not segs:
        raise PackError("no loadable data")
    if elf.entry % 4 or not any(a <= elf.entry < a + len(d) for a, d in segs):
        raise PackError("entry point 0x%x is not in a loaded segment"
                        % elf.entry)
    return segs


def pack_section(elf):
    """Builds the packed section data (format spec §4): header, an empty
    chunk list, the segments stored uncompressed, the load directory and
    the loader stub.  Returns the bytes."""
    segs = plan_segments(elf)
    body = bytearray(struct.pack(">I", 0))   # 0x20: end of the chunk list
    records = []
    for addr, data in segs:
        records.append((REC_COPY, 0x20 + len(body), addr,
                        len(data) // 4, 1))
        body += data
    for sym, rtype in (("__mipsx_cb0", REC_CB0), ("__mipsx_cb1", REC_CB1)):
        if sym in elf.symbols:
            records.append((rtype, elf.symbols[sym] >> 2, 0, 0, 0))
    records.append((REC_ENTRY, ENTRY_FLAG | (elf.entry >> 2), 0, 0, 0))
    dir_off = 0x20 + len(body)
    directory = b"".join(struct.pack(">5I", *r) for r in records)
    stub = struct.pack(">%dI" % len(STUB_WORDS), *STUB_WORDS)
    length = dir_off + len(directory) + len(stub)
    if length > MAX_SECTION_LENGTH:
        raise PackError("section is 0x%x bytes; the boot selector accepts at "
                        "most 0x%x (format spec §3)"
                        % (length, MAX_SECTION_LENGTH))
    stack = elf.symbols.get("__stack_top", DEFAULT_STACK)
    header = struct.pack(">6I8x", PACKED_MAGIC, dir_off, len(records), stack,
                         length, length - 0x10)
    section = bytearray(header + body + directory + stub)
    struct.pack_into(">I", section, length - 4, length)
    assert len(section) == length and length % 4 == 0
    return bytes(section)


def table_entry(stype, data, version):
    """A section table entry (format spec §3)."""
    check_version(version, "section version")
    enc = version.encode("ascii")
    if len(enc) > 0x53:
        raise PackError("section version longer than 83 characters")
    e = bytearray(HEADER_SIZE)
    struct.pack_into(">II", e, 0x00, 0, TAGS[stype])
    e[0x08] = stype
    struct.pack_into(">I", e, 0x0C, HEADER_SIZE)
    e[0x10:0x20] = hashlib.md5(data).digest()
    struct.pack_into(">II", e, 0x20, len(data), 0)
    e[0x28:0x28 + len(enc)] = enc        # NUL-padded; 0x7C-0x7D stay zero
    struct.pack_into(">H", e, 0x7E, sum(e[0:0x7E]) & 0xFFFF)
    return bytes(e)


def build_image(sections, version):
    """SECTIONS is a list of (type, data, section version).  Returns the
    upgrade image (format spec §1-§3, §6)."""
    check_version(version, "image version")
    enc = version.encode("ascii")
    if len(enc) > 31:
        raise PackError("image version longer than 31 characters")
    if not 1 <= len(sections) <= TABLE_ENTRIES:
        raise PackError("an image holds 1 to 3 sections")
    entries = [table_entry(t, d, v) for t, d, v in sections]
    length = SECTIONS_START + sum(HEADER_SIZE + len(d) for _, d, _ in sections)
    hdr = bytearray(HEADER_SIZE)
    hdr[0:16] = IMAGE_MAGIC
    struct.pack_into(">III", hdr, 0x50, HEADER_SIZE, HEADER_SIZE, length)
    hdr[0x5C:0x5C + len(enc)] = enc
    struct.pack_into(">I", hdr, 0x7C, len(sections))
    first = bytearray(hdr + b"".join(entries))
    first += bytes(SECTIONS_START - len(first))       # unused table entries
    first[0x30:0x40] = hashlib.md5(first).digest()    # field zero meanwhile
    out = bytearray(first)
    for e, (_, d, _) in zip(entries, sections):
        out += e + d
    assert len(out) == length
    return bytes(out)


def pack_elf(elf_bytes, version="9.0.0", section_version=None):
    """ELF bytes in, image bytes out: one type 2 section."""
    elf = Elf(elf_bytes)
    data = pack_section(elf)
    if (HEADER_SIZE + len(data) + 0xFFFF) & ~0xFFFF > APP_FLASH_SPACE:
        raise PackError("section of 0x%x bytes would not fit in flash below "
                        "0xF0000 without overwriting the recovery program "
                        "(tools/README.md)" % len(data))
    return build_image([(2, data, section_version or version)], version)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Pack a linked MIPS-X ELF into an SPA3000 upgrade image "
        "with one type 2 section.")
    p.add_argument("elf")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--version", default="9.0.0",
                   help="image version, N.N.N or N.N.N(text) (default "
                   "9.0.0); the installers refuse 0.x, 1.0.x and 2.0.x")
    p.add_argument("--section-version",
                   help="version string in the section entry (default: "
                   "--version)")
    args = p.parse_args(argv)
    try:
        with open(args.elf, "rb") as f:
            image = pack_elf(f.read(), args.version, args.section_version)
    except (OSError, PackError) as ex:
        sys.stderr.write("mipsx-pack: error: %s\n" % ex)
        return 1
    with open(args.output, "wb") as f:
        f.write(image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
