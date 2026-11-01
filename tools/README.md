# tools: image packer, verifier and recovery client

Work package S7 of the LLVM backend plan. All three are Python 3 scripts that
use only the standard library, written from the
[firmware image format spec](https://github.com/openmipsx/devices/blob/main/common/firmware-image-format.md)
("format spec") alone. They contain no vendor code or data, and the tests use only our
own programs.

| File | What |
|---|---|
| `mipsx_pack.py` | ELF in, upgrade image out: one type 2 section |
| `mipsx_verify.py` | Re-reads an image with the format spec's rules only; shares no code with the packer |
| `mipsx_recover.py` | Sends an image to a unit running its recovery program (section B) over the multicast recovery protocol, and serves it by TFTP |
| `loader-stub.s` | Source of the loader the packer puts at the end of the section (assembled words are in `mipsx_pack.py`; a test checks they match) |
| `tests/test_tools.py` | Packer, verifier, corrupt images, and the packed image run on the simulator |
| `tests/test_recover.py`, `tests/fake_unit.py` | The recovery client against a fake section B on loopback, and its messages byte for byte |

```
python3 tools/mipsx_pack.py prog.elf -o prog.bin --version 9.0.0
python3 tools/mipsx_verify.py -v prog.bin
python3 tools/mipsx_recover.py discover
sudo python3 tools/mipsx_recover.py upgrade prog.bin
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

## The recovery client

`mipsx_recover.py` is the clean-side replacement for the vendor's Windows
recovery tool: a way to put an application back on a unit whose
application no longer boots, before any experimental image is flashed.
It speaks the protocol of format spec §7.1 to section B (§5, "What
section B does") and nothing else; it cannot reach a unit that is
running its application or that has no working section B.

```
python3 tools/mipsx_recover.py discover [-v]
sudo python3 tools/mipsx_recover.py upgrade prog.bin [--target ID] [-v]
python3 tools/mipsx_recover.py upgrade prog.bin --tftp-port 0   # unprivileged
```

What `upgrade` does, with the spec reference for each step:

1. Runs `mipsx_verify.py`'s checks over the image (`--no-verify` to skip)
   and reports its version and section types. Section B writes only
   sections of type 2 and above (§5, Installing, step 8), so types 0 and
   1 in the image are reported as skipped, and an image with no type 2
   section gets a warning: installing it clears the application slot
   (§6).
2. Opens two sockets: one bound to port 4811 (replies come there, and
   requests go from there) and one bound to the TFTP port, both joined to
   234.4.8.10. The TFTP socket is joined because the unit sends its read
   request **to the group** at the port named in the request, and its
   acknowledgements to the socket that answered (§7.1), so one socket
   must do both.
3. Sends a type 0 discovery request (160 bytes: type at 0, `RECM` at 4,
   target `FFFFFFFFFFFF` or `--target` at 8) to 234.4.8.10:4810 and
   collects type 1 replies for 2.5 s. Exactly one unit must answer, or
   the one named by `--target`; with `--any` this step is skipped and the
   upgrade request is addressed to every unit.
4. Sends the type 2 request with the TFTP port at 0x1C and the file name
   at 0x20, addressed to the unit found, and reports the acknowledgement
   (the request echoed, cut to 100 bytes).
5. Answers the unit's TFTP read request for that name (octet mode only;
   other names and modes get a TFTP error) with 512-byte blocks, each
   acknowledged before the next, resending a block up to 5 times after
   5 s without an acknowledgement. Progress is printed every tenth of
   the file.
6. Waits 30 s, then sends a discovery addressed to the unit. The spec
   says a unit that installed the image stops and waits for a power
   cycle, and one that rejected it goes on listening (§5, §7.1), so
   silence is reported as probable success (exit 0) and a reply as
   probable failure (exit 2). `--no-post-check` skips this.

`-v` hex-dumps every datagram sent and received. Every datagram arriving
on either socket that is not what the client is waiting for is reported
rather than dropped silently.

**Open points in the format spec.** §7.1 fixes the ports, group, the
160-byte request, the magic, the types and the field offsets. The
following it either leaves open or has only from the third-party
description, "unconfirmed on the SPA3000". Each is an option, defaulting
to the most conservative reading; all of them are questions for the
dirty side to settle with a capture of the vendor tool, or on the board
model.

| # | Open point | What the client does | Option |
|---|---|---|---|
| R1 | Where replies go: to the group at 4811 or to the sender at 4811 (§7.1 says the decompiler hides the address). | Binds 4811 on every address and joins the group, so both arrive. | `--reply-port`, `--interface` |
| R2 | Which source port the unit expects requests from. The public description says the client sends from 4811; the spec does not say the unit checks. | Sends from the 4811 socket. | `--reply-port` |
| R3 | Width and byte order of the TFTP port field at 0x1C: a 16-bit port, or a 32-bit word? Nothing between 0x1C and 0x20 is otherwise described. | 16-bit big-endian at 0x1C, bytes 0x1E–0x1F zero. | `--port-width` (16 or 32) |
| R4 | Width of the identifier field: 20 bytes per the public description; the spec says only "NUL-terminated from offset 8". What the identifier *is* (the factory record's +0x20 string is a Hypothesis for the serial number) and whether the type 1 reply's identifier is exactly the string that matches. | Accepts 1–19 characters; addresses the upgrade to the identifier the unit's own reply gave. | `--target`, `--any` |
| R5 | Whether the unit requires a particular TFTP port (69?) or accepts any. | Default 69, which needs privileges on Linux. | `--tftp-port` (0 picks a free port) |
| R6 | How much of the file name the unit uses: 67 bytes per the public description. | Refuses names of 67 or more characters. | `--name` |
| R7 | Whether the unit's TFTP client sends options (RFC 2347 `blksize`, `tsize`) and whether it accepts a server that ignores them. | Ignores options and sends plain 512-byte blocks, as RFC 2347 allows. | — (reported in the log) |
| R8 | Whether the read request names the file in octet mode. | Serves octet only; refuses other modes. | — (reported) |
| R9 | TFTP timing: how long the unit waits for a block and whether it retransmits acknowledgements. | 5 s per block, 5 resends. | `--block-timeout`, `--block-retries` |
| R10 | How long after the acknowledgement the read request comes, and how long the install takes (erase, write, read back and repeat, §5 step 8). | 60 s for the read request; 30 s before the post-check. | `--rrq-timeout`, `--install-wait` |
| R11 | How the result is reported: §5 says error codes exist but "their reporting path was not traced", and a successful install stops without restarting. | Infers it from whether the unit still answers discovery. | `--no-post-check` |
| R12 | Whether a lost type 2 request may be resent without starting a second upgrade; whether the acknowledgement always comes. | Never resends a type 2 request; waits for the read request even without an acknowledgement. | `--repeat` (discovery only) |
| R13 | Multicast TTL and the interface the vendor tool uses. | TTL 1, the system's default interface. | `--ttl`, `--interface` |
| R14 | Whether the unit answers a unicast request to its own address (the spec describes only the group). | Sends to the group. | `--unicast ADDR` |
| R15 | The meaning of the two bytes at 0x62 of the type 1 reply. | Printed as hex. | — |

**Tests** (`tests/test_recover.py`) run the client against
`tests/fake_unit.py`, a fake section B written again from the spec's
description (§5 main loop and installer steps 2–8, §7.1 message layouts)
that shares no code with the client. Everything runs on loopback with
unicast addresses and free ports (the group, ports and timings are
options), so no root and no network are needed. The tests cover
discovery (one unit, two units, targeted requests ignored by the other
unit, replies to the group, repeated requests, junk on the reply port),
the whole upgrade (image delivered intact, the fake's installer writes
exactly the image's type 2 section, acknowledgement echo, 32-bit port
field, dropped blocks resent, `--any`, a unit that rejects an image and
keeps listening), the TFTP server alone (block boundaries, drops, wrong
name and mode, a peer that never acknowledges) and the command line.
The packet-level check builds each request the spec describes by hand
(type, `RECM`, target, port, name at their offsets, zero elsewhere) and
compares it with what the fake unit received, and checks every TFTP
block against RFC 1350 and the image.

## Not done yet

- Link-testing with lld (S5): the tests build ELFs with
  `sim/tests/mxasm.py`. Once lld exists, pack an lld-linked program and
  check the result still runs in the simulator test.
- Writing more than one section, or deflate-compressed segments.
- The recovery client has run only against the fake unit. Before it is
  trusted with a real unit, confirm R1–R6 on the wire (a capture of the
  vendor tool talking to a unit in recovery mode would settle most of
  them) and run it against the recovery program on the board model.
