# tools: image packer and verifier

Work package S7 of the LLVM backend plan. Both are Python 3 scripts that
use only the standard library, written from the
[firmware image format spec](https://github.com/openmipsx/devices/blob/main/common/firmware-image-format.md)
("format spec") alone. They contain no vendor code or data, and the tests use only our
own programs.

| File | What |
|---|---|
| `mipsx_pack.py` | ELF in, upgrade image out: one type 2 section |
| `mipsx_verify.py` | Re-reads an image with the format spec's rules only; shares no code with the packer |
| `loader-stub.s` | Source of the loader the packer puts at the end of the section (assembled words are in `mipsx_pack.py`; a test checks they match) |
| `tests/test_tools.py` | Packer, verifier, corrupt images, and the packed image run on the simulator |

```
python3 tools/mipsx_pack.py prog.elf -o prog.bin --version 9.0.0
python3 tools/mipsx_verify.py -v prog.bin
make check                      # at the top level: runs these tests too
```

Python was chosen over C because the packer and verifier are small,
need MD5, deflate and CRC-32 (all in Python's standard library), and do
not need to be fast.

## The image

Only a **type 2** (application) section, so a stock installer never
replaces the boot section or the recovery program (stack plan §3.5,
format spec §5 and §7.2).

| Offset | Content |
|---|---|
| 0x000 | Global header (format spec §2): magic, MD5 of 0x000–0x0FF with 0x10–0x3F zeroed, header size 0x80, entry size 0x80, file length, version (default `9.0.0`), section count 1 |
| 0x080 | Table entry for the section (§3): tag 0xCACAD3C3, type 2, data offset 0x80, MD5, length, version, byte sum at 0x7E |
| 0x100 | Copy of the table entry, then the section data |

The installers compute the first section's offset, and the extent of
the global MD5, from the header as 0x50 + 0x54 × 0x7C (format spec §2,
§6 step 4): 0x100 with one section, 0x200 with the stock three. The
table holds only the counted entries; nothing is padded to three slots.

Section data (format spec §4):

| Offset | Content |
|---|---|
| 0x00 | Packed header: 0x00060803, directory offset, record count, stack (`__stack_top`, else 0x1FFFF0), length, length − 0x10, zero |
| 0x20 | A zero word: the chunk list is empty |
| 0x24 | Each PT_LOAD segment's file bytes, uncompressed, padded to words |
| … | Load directory: one 0x01 record per segment (copy *word 3* words from header offset *word 1* to *word 2*; the form section C uses, §5; word 4 = 1, the relocation nibble that makes word 1 header-relative, §4.4), then 0x07 (`__mipsx_cb0` / 4), 0x05 (`__mipsx_cb1` / 4), and 0x03 last (entry word address, bit 30 set as in the stock images); words 2–4 of those three are zero (§4.4 says to zero the "Varies" words) |
| … | The loader stub (`loader-stub.s`, 304 bytes) |
| length − 0x10 | Its entry: a branch back to the stub's start, two `nop` slots |
| length − 4 | The section length (the stub uses it to find the header) |

Segment bytes beyond the file size (`.bss`) are not stored: crt0 clears
`.bss`. No 0x02 (zero-fill) or 0x10 (deflate) records are written.

## The loader stub

The boot selector jumps to data + length − 0x10 in flash (format spec §5,
step 4). Where the section lies in flash depends on who installed it
(section A rounds to 64 KB, section B packs to 4 bytes), so the stub is
position-independent: it writes a return instruction to RAM at 0x1FF0,
calls it to learn its own address, reads the length from the section's
last word, and finds the header. It then copies each 0x01 record to RAM,
sets r23/r24 from 0x07/0x05, and jumps to the 0x03 entry with r4 = header
address. It does not use the boot section's decompression service (§4.6),
so it does not depend on the stock boot section beyond its checks.

The tests run it on the simulator: the section is placed in "flash" (RAM
above 4 MB) at a sector boundary and at an odd word offset, entered at
length − 0x10, and must print and exit through crt0.

## What the verifier checks

Every check the format spec attributes to the boot selector or an
installer, plus the structure it describes:

- Header: size at least 0x100, magic, reserved fields zero, 0x50/0x54 =
  0x80, length = file size, version a NUL-padded string that the
  installers accept (not major 0, 1.0.x or 2.0.x), count 1–3, size at
  least 0x50 + 0x54 × 0x7C, and the global MD5 over exactly that many
  bytes with 0x10–0x3F zeroed (§2).
- Each counted entry: field 0x00 zero, known type with its tag, data
  offset 0x80, length ≤ 0xFFFFF, 0x24 zero, version string, bytes
  0x7C–0x7D zero, the byte sum at 0x7E and the boot selector's
  word-at-0x7C form of it, the entry copy equal to the table, the data
  MD5; sections contiguous from 0x50 + 0x54 × 0x7C to the end of the
  file. Nothing is read beyond the counted entries, as in the installers.
- Packed sections: header magic, length fields, reserved zero, stack
  8-aligned in RAM, the word at length − 0x10 a branch into the section,
  the chunk list, the directory inside the section, 0x01 copies inside
  the payload and RAM, 0x10 streams (pre-words not redirecting the
  stream elsewhere, raw deflate, CRC-32 and length trailer), 0x02
  zero-fills (length in words) in RAM, no overlapping loads, the
  register records (0x05–0x0C) known, word 4 = the relocation nibbles
  §4.4 gives (1 for 0x01 and 0x10 records, 0 otherwise), the "Varies"
  words zero, exactly one 0x03 record, last, pointing into loaded data,
  and the 0x07 value = a loaded range's word address + 0x10000 (the
  §4.4 rule).
- Our rules: only type 2 sections (`--allow-types` to relax), and the
  type 2 sections, rounded to 64 KB, fit in the 0xB0000 bytes of flash
  between the stock recovery program and 0xF0000.

The tests flip every byte of a packed image in turn and check that the
verifier notices each one, and check the named error for 40
specific corruptions (with checksums recomputed so that the check behind
them is reached), that a one-section image has its section at 0x100
and its MD5 over 0x100 bytes, and that an image laid out with three
table slots and the section at 0x200 is rejected.

## Decisions and risks (read before flashing)

- **Version 9.0.0 by default**, above the stock 3.1.20, so that neither
  installer refuses it as a downgrade. The per-model floor and the
  provider's minimum (format spec §7.2) are not known.
- **One table entry, section at 0x100, MD5 over 0x100 bytes.** Earlier
  versions of the packer padded the table to three slots and started
  the section at 0x200 with a 0x200-byte MD5, which is what a stock
  three-section image has. The format spec now records (§2, Q2) that
  both installers compute the first section's offset and the MD5 extent
  from the header fields, never read table entries beyond the count,
  and refused an image laid out the old way as corrupt while accepting
  the same section at 0x100. The verifier rejects the old layout.
- **Stub assumptions to confirm on hardware:** that RAM at 0x1FF0 is free
  when the boot selector hands over, that freshly written RAM can be
  executed without cache maintenance, and that the boot selector enters
  with nothing else expected of the section (the stock stubs' entry
  conditions are not in the spec).
- The 0x07/0x05 records are written for conformity with the stock
  layout; crt0 sets r23/r24 itself anyway.
- Do not flash anything until the recovery question (format spec Q7,
  stack plan §3.5) is settled.

## Not done yet

- Link-testing with lld (S5): the tests build ELFs with
  `sim/tests/mxasm.py`. Once lld exists, pack an lld-linked program and
  check the result still runs in the simulator test.
- Writing more than one section, or deflate-compressed segments.
