# examples/blink: the first SPA3000 image

Step 2 of the open-source stack plan (§4): an image that the stock boot
section loads, which blinks the status LEDs. It also kicks the watchdog,
and it carries a **dead-man net** so that a unit on which it hangs still
reaches the stock recovery program. Written from the specifications in
openmipsx/devices (`spa3000/peripherals.md`, `spa3000/flash.md`,
`common/firmware-image-format.md`, `common/processor-es3890.md`) and
the Am29LV081B datasheet; no vendor code.

**Status: never run on the board.** Both variants build, pack, pass
`tools/mipsx_verify.py`, and run on the simulator as far as the
simulator can take them (§6). Every fact the image depends on that the
specs mark Hypothesis is listed in §8, and what the specs do not say in
§9. Read both before flashing.

| File | What |
|---|---|
| `main.c` | Start-up order and the blink loop |
| `board.c`, `board_io.h` | Watchdog kick, system-control port, port 0 LEDs, timer |
| `flash.c`, `flash.h` | Am29LV081B driver (identify, sector erase, byte program) |
| `bootrec.c`, `bootrec.h` | Boot record reading and the dead-man net |
| `board.h`, `hal.h`, `util.*` | Addresses from the specs; the volatile accesses; `memcpy` and friends |
| `vectors.S` | A no-op and a jump to a stop loop at address 0 |
| `sim/model.c` | Timer, system-control and flash models for the simulator build |
| `tests/test_blink.py` | Image, loader stub and model tests (`make check`) |

## 1. Building

```
cd examples/blink
make MIPSX_LLVM_BIN=/path/to/llvm-project/build/bin SYSROOT=/path/to/mipsx-sdk/build/sysroot
make check MIPSX_LLVM_BIN=... SYSROOT=...     # needs sim/build/mipsx-sim
```

`SYSROOT` defaults to the SDK's `build/sysroot` (`make sysroot` at the
top level builds it). Outputs:

| File | Variant |
|---|---|
| `blink.bin` | **Variant 1.** Kicks the watchdog, never writes system-control reg 3 (does not enable it) |
| `blink-wd.bin` | **Variant 2.** The same, and enables the watchdog (reg 3 = 0xBC) once kicking runs |
| `blink-sim.elf` | The simulator build (§6), not an image |

Build options go in `make CFLAGS_EXTRA=...`: `-DARM_SECONDS=N`
(default 15: seconds of blinking before the record is restored) and
`-DBLINK_KICK_STOP_S=N` (default 0: stop kicking N seconds after the
restore, for the watchdog time-out experiment, §7).

The image version is 9.0.1, above the stock 3.1.20, so that neither
installer refuses it as a downgrade (`tools/README.md`). The image holds
one type 2 section of about 7 KB, so the stock application's installer
puts it in the one 64 KB sector below the factory record, flash 0xE0000
(format spec §7.2), and its table entry at 0x0C0E0000 goes into the
boot record's type 2 slot.

## 2. What the image does

In this order (`main.c`; the numbers in the LED table below refer to
these stages):

1. **Interrupts stay masked.** PSW bit 4 is set (processor spec §10) and
   the interrupt enable register 0x20004034 is cleared (peripherals.md
   §7.2 step 1). Nothing ever enables an interrupt. Address 0 holds a
   no-op and a jump to a stop loop (`vectors.S`) in case an exception
   arrives there anyway.
2. **Watchdog kick** (§5): 0x20004028 = 9 then 0x2000402C = 0x32, again
   0x20004028 = 9 then 0x2000402C = 0x36. Kicks repeat at every LED
   toggle (every 0.5 s, half the 2–3 s the spec asks for) and inside the
   flash driver's polling loops.
3. **The dead-man net** (§3): the boot record is rewritten without this
   program's slot. The LEDs are not yet touched, so they stay as the
   boot code leaves them (off, if port 0 bit 3 is released then).
4. **Timer and LEDs.** 0x20004008 = 0xFF, 0x2000400C = 0, 0x20004014 = 0
   (§7.2 step 7, the plain timer writes; the timer control written by
   the reset code, §7.1, is left alone). Port 0 data 0x08 then direction
   0x08: bit 3 driven high, LEDs off (§6, data before direction). Only
   bit 3 is driven; the Ethernet, SLIC and DAA reset pins stay released.
   Variant 2 now writes system-control reg 3 = 0xBC and kicks twice (§5,
   §7.2 step 13).
5. **Blink.** Bit 3 toggles between driven 0 (on) and driven 1 (off)
   with the timer at 0x2000400C counting CPU cycles at 81 MHz (§4):
   every 500 ms when the net is armed or restored, every 1000 ms when
   the net was skipped, every 125 ms after a flash failure. If the
   timer count does not change in 100,000 consecutive reads, the program
   falls back to a counted loop and the LEDs blink at some other rate.
6. **Restore.** After 15 s of blinking (variant and timer permitting)
   the record is rewritten with the slot back. The LEDs pause for the
   second or two that takes, then blink on.

None of the stock firmware's other start-up writes (§7.2 steps 3 to 6,
8, 9 and 11: DMA, DSP, the unknown blocks, and the system-control
clock/PLL registers) are made. If the LEDs blink but not at 0.5 s, that
is where to look first (§8, H5).

| LEDs D4, D7, D8 (INTERNET, LINE, PHONE) | Meaning |
|---|---|
| Off for 1–2 s after power-on, then blinking | Normal: stage 3 erased a 64 KB sector (0.7 s typical, 15 s maximum) and copied the configuration area |
| Toggling every 0.5 s | Net armed or restored; CPU clock and timer as the spec says |
| A pause of 1–2 s about 15 s in, then toggling again | The restore (stage 6). From here on a reset starts this image again |
| Toggling every 1 s | Net skipped: no boot record, the type 2 slot unused, the slot's section is not this program, or the flash did not identify as an Am29LV081B (nothing was written) |
| Toggling every 0.125 s | A flash erase or program failed after retries; the active block is untouched |
| Toggling at some other steady rate | The timer is not counting as §4 says (fallback loop), or the CPU clock is not 81 MHz |
| Nothing, ever | The image was not started, or stopped before stage 4: see §5 |
| Blinking, then dark, then the pattern starts over | A reset: with variant 2, the watchdog fired (the kick is wrong); see §7 |

D1 (the Power window) is driven by the RTL8019AS, not by this image
(hardware.md §1); ignore it.

## 3. The dead-man net

**The problem** (format spec §5 "Order", §7.2, Q7). The boot selector
starts whatever the newest boot record's type 2 slot points at, every
time, and an application cannot ask for section B. An application that
passes the boot checks and then hangs is therefore started forever, and
with one unit and no in-circuit flash backup that would be the end of
the experiment.

**The net** (`bootrec.c`). Section B, the stock recovery program, is
started when the record's type 2 slot is unused and the type 1 slot is
valid (§5 "Order" step 2; §6, Simulated with a record holding only its
type 1 slot). So:

1. At every start, before anything that could hang, the image writes a
   new record into the **inactive** block (sector 0 or 1, whichever
   does not hold the newest record) with the sequence number increased
   by one and the type 2 slot blanked to 0xFF. From now on a reset
   starts section B.
2. After 15 s of blinking it writes another record into the other block,
   sequence number increased again, with the type 2 slot restored from
   the record it found. From now on a reset starts this image.

Each write does what sections A and B do (§5 "Boot-record blocks"):
erase the inactive block; copy the active block's 0x400–0xFFFF across
unchanged (the image-header copy, the event log, the configuration
store and its mirror; the installers copy 0x1000–0xFFFF and rewrite the
header copy, so this keeps more, not less); write the record with its
first byte last, so that a block with an incomplete `SIPURA *` is never
taken as valid; read everything back. The record written is the record
found, with only the sequence number, its complement and the type 2
slot changed. Nothing is invented: the halfword pairs at +0x10 and
+0x14 (meaning unknown, Q6), the type 1 slot and any further slots are
copied.

Before writing anything the image checks, in order, and otherwise
leaves the flash alone (the 1 s blink):

- the chip answers the autoselect command with 01h / 38h (Am29LV081B);
- one of the two blocks holds `SIPURA *`; with both valid the higher
  sequence number wins, and block 1 on a tie, as sections A and B
  choose (§5; the selector's tie rule is not known, §9);
- the type 2 slot is usable (address not 0xFFFFFFFF, address OR check
  = 0xFFFFFFFF, §5);
- the section that slot points at **loads this very program**: the
  image walks the packed section's directory (§4.1, §4.4) and compares
  every 0x01 record's bytes in flash with RAM at its load address. That
  is also a check that the installer wrote the section faithfully. It
  runs before any `.data` variable is written.

The driver refuses to erase any sector other than 0 and 1, so no bug in
this program can reach section B at 0x20000, the application, the
factory record at 0xF0000 or the boot section (flash.md §6).

**What each failure leads to.**

| Event | Flash afterwards | Next reset starts |
|---|---|---|
| Hang or power loss before the arm write starts | Unchanged | This image, again (the one case the net cannot cover) |
| Power loss during the arm write | New block has no complete magic; old record intact | This image |
| Hang after arming (stages 3–5) | Record without the slot is newest | **Section B** |
| Power loss during the restore write | Record without the slot is newest | Section B |
| Hang after the restore | Record with the slot is newest | This image (it ran 15 s first) |
| Flash erase or program failure | Active block untouched; inactive block partly written, magic incomplete | This image |

So **during the first 15 s of every start, a power cycle gets you into
section B.** That is also the way back to the stock firmware (§5).

Costs: two sector erases per start (the part is rated for a million per
sector); 1–2 s of dark LEDs at start and a pause at 15 s; the event log
and configuration store are copied, not lost. The sequence number grows
by two per start.

## 4. Flashing through the stock web UI

Do not do this until the checklists in §8 and §9 have been read, and
`tools/README.md` ("Decisions and risks") with them. Have the stock
image file (3.1.20(GW)) at hand for the way back; it is not in this
repository.

1. Build and check:

   ```
   make MIPSX_LLVM_BIN=... SYSROOT=...
   python3 ../../tools/mipsx_verify.py -v blink.bin
   ```

   The verifier must report no error. Look at its listing: one type 2
   section, loads at 0x0 (the 16-byte vector), 0x2000 (the program) and
   just after it (16 bytes of small data), entry 0x2000, and the section
   length a multiple of 4 (§6: a misaligned start stops the boot
   selector with no fallback).

2. Serve `blink.bin` by TFTP from a PC on the same LAN (format spec §7:
   the stock upgrader does exactly this). Any TFTP server will do, for
   example `tftpd-hpa` or `dnsmasq --enable-tftp`, with `blink.bin` in
   its root.

3. Ask the unit to fetch it:

   ```
   http://<unit's address>/admin/upgrade?tftp://<PC's address>/blink.bin
   ```

   If an admin password is set the request is authenticated (HTTP
   Digest, §7). The application downloads the whole image, checks the
   global MD5, the version (9.0.1 is above the stock 3.1.20 and the
   per-model floor is not known, §7.2), every entry's byte sum and
   section MD5, writes the section to flash 0xE0000, writes a boot
   record with the type 2 slot pointing at it to both blocks, logs the
   version and restarts (§7.2). Q10 of the format spec: on the board
   model the installer wrote the section where expected but what it did
   next could not be reproduced, so the install-then-boot path is
   unverified end to end.

4. Watch the LEDs (§2). Note the time from power-on to the first blink
   and the toggle period; both are measurements the specs want (§4's
   81 MHz, §5's timing).

5. Flash variant 2 (`blink-wd.bin`) the same way, from section B (§5)
   or by first going back to the stock application. If variant 1 blinks
   steadily and variant 2 resets after a steady interval, the kick is
   wrong and the interval is the watchdog time-out. If both blink
   steadily, the kick works (or there is no watchdog); see §7.

## 5. Recovery

**Into section B.** Power-cycle the unit within the first 15 s of a
start (the net is armed). The selector then finds no type 2 slot and
tries the type 1 slot, which the stock installer left pointing at
section B at 0x20000; if that slot is somehow absent, its scan finds
section B there anyway, before any type 2 section (§5 "Order" step 3).
If the image hung before arming, or never started, the record still
points at it and section B is reached only if the image fails the
selector's checks, which an image that passed them once will not; the
remaining route is a flash programmer (hardware.md H7).

**Section B's behaviour** (§5 "What section B does"): it brings up the
network (stored address or DHCP, else it probes 192.168.1.100–200,
192.168.2.100–200 and 192.168.3.100–200), then answers the recovery
protocol and retries any stored upgrade rules. It has no web server.

**The recovery protocol** (§7.1). UDP port 4810, multicast group
234.4.8.10, 160-byte messages with the magic `RECM` at offset 4 and a
target identifier (the unit's serial number, or `FFFFFFFFFFFF` for any
unit) at offset 8. Type 0 is discovery, answered with a 100-byte type 1
reply to the group at port 4811 giving the identifier, model, MAC,
versions and address. Type 2 asks for an upgrade: the unit fetches the
file named at offset 0x20 by TFTP from 234.4.8.10 at the port given at
0x1C (the server must answer from the socket it sent the read request
to), checks it like a normal upgrade (the same version rules), writes
only its type 2 sections, rewrites the boot record, and then **stops
and waits for a power cycle**. A client for this protocol is a separate
task; the stock image, or a corrected blink image, is what to send.

**Back to the stock firmware.** Send the stock image through section B
as above. Its type 0 and 1 sections are not written (section B never
replaces itself or the boot section), its application goes back in, and
the next power cycle starts it.

## 6. Simulator tests

`make check` runs `tests/test_blink.py`:

- Both images pass the verifier, hold one type 2 section with loads at
  0 and 0x2000 (and the small data after it), and differ from each
  other.
- Each image is started on `mipsx-sim` as the boot selector would start
  it (section placed in RAM above 4 MB at a sector boundary and at an
  odd offset, entered at data + length − 0x10, as `tools/tests` does).
  The loader stub copies the program, crt0 runs, and `main` sets the
  PSW and then makes its first peripheral access, a store to 0x20004034,
  which the simulator (no peripherals) reports as unmapped. The test
  checks exactly that: the image gets from the boot selector into
  `main` at both placements.
- `blink-sim.elf`, built with `-DBLINK_SIM -DARM_SECONDS=3`, runs the
  whole start-up against `sim/model.c`: the timer advances 1 ms per
  read, the system-control device logs register writes and LED
  changes, and a model of the Am29LV081B written from the datasheet
  (unlock sequences, autoselect, program with 1 → 0 only, sector erase,
  DQ7/DQ6/DQ5 polling) holds a boot record pair and a copy of the
  program laid out as the packer lays a section out. The tests check
  the net end to end (armed into the inactive block, restored into the
  other, sequence numbers, the 0x400–0xFFFF copy, the LED period, data
  written before direction) and every reason to leave the flash alone:
  no record, equal sequence numbers, an erased second block, the type 2
  slot unused, a section that is not this program, a chip with the
  wrong ID, a stuck timer, and erase and program failures (DQ5).

No board model exists on this branch (`--board=spa3000` is not an
option of this simulator), so the device image itself runs only to its
first peripheral access.

## 7. The watchdog question (peripherals.md P1)

Variant 1 never sets reg 3 bit 7; variant 2 sets it after kicking has
started. Both kick. Readings:

- Variant 1 resets on its own: the watchdog runs from reset and the
  kick does not satisfy it (or something else resets the chip).
- Variant 1 steady, variant 2 resets every T seconds: the kick is
  wrong and T is the time-out, or longer than T is needed.
- Both steady: the kick works; whether the watchdog runs from reset is
  still open. Build with `-DBLINK_KICK_STOP_S=60`: 60 s after the
  restore the image stops kicking while it goes on blinking. The time
  from then to the restart (LEDs dark, then the pattern starts over) is
  the time-out; no restart within minutes means the watchdog is off in
  that variant. The restart goes through the boot code and starts this
  image again (the record was restored), so this is safe to try.

## 8. Hypotheses this image depends on

Each is a fact the specs mark Hypothesis (or that only the stock
firmware's behaviour supports), with what happens here if it is wrong.

| # | Fact | Where | If wrong |
|---|---|---|---|
| H1 | The boot selector starts the type 2 slot's section by jumping to data + length − 0x10, with the loader stub's entry conditions (RAM at 0x1FF0 free, code runnable from freshly written RAM, nothing else expected of the section) | format spec §5 "Order" step 4; `tools/README.md` | Nothing blinks; the selector stops or runs garbage. Recovery needs a flash programmer unless the selector falls back |
| H2 | Interrupts are masked at hand-over, or masking them with PSW bit 4 (the manual's M bit) works; exceptions enter at word 0 | processor spec §10 (strongly supported) | A stray interrupt or exception goes to address 0 and stops (variant 2: resets) |
| H3 | 0x2000400C counts up once per CPU cycle, at 81 MHz, without an interrupt enabled and after only the §7.2 step 7 writes | peripherals.md §4 (strong), §2 | Period other than 0.5 s, or the fallback loop's rate |
| H4 | The watchdog kick is the low-then-high pulse on 0x2000402C bit 2 with 0x20004028 = 9 before each write; its time-out exceeds 0.5 s; it is off from reset (or on, and the kick satisfies it) | §5 (strong) | Variant 1 resets (watchdog on from reset and kick wrong), or variant 2 resets at the time-out |
| H5 | Port 0 of the system-control device works with none of the stock firmware's other system-control writes (regs 0, 1, 2, 0x22, 0x23, 0x40, 0x43, 0x46, 0x47, 0x63, 0x64, 0x70) and none of the §7.2 step 3–6 on-chip writes; the CPU runs at 81 MHz without the reg 0x43/0x46/0x47 PLL values | §3, §7.2 step 11 (roles unknown) | LEDs dark (port 0 not reached) or wrong rate (clock) |
| H6 | The two-step byte protocol at 0x14000003 (address byte reg << 1 \| rw, then data), with 0x20004028 = 0 before each access, and address bits 1–0 not decoded | §3 (Observed) | LEDs dark |
| H7 | Port 0 bit 3 (AUX1[3], pin 111) drives D4, D7, D8 through Q21 as a high-side switch: driven 0 = on, driven 1 = off; data then direction is the right order | §6, hardware.md H4 | LEDs inverted or dark |
| H8 | Port 0's other bits are released before the first write and may stay released (Ethernet, SLIC and DAA resets, Si3050 CS#) | §6 (Hypothesis) | Nothing for the LEDs; the other chips are in whatever state the boot code left |
| H9 | The flash is an Am29LV081B at 0x0C000000, byte-wide, with the CPU's byte address n reaching flash byte n, commands and reads working through the 0x1C000000 alias (the form the stock driver uses), and WE# wired so the CPU can write | flash.md §1, peripherals.md §1 | Identify fails (1 s blink, flash untouched), or writes fail (0.125 s blink) |
| H10 | The boot record format of format spec §5: `SIPURA *`, sequence at +0x08 (higher wins; both blocks compared), complement at +0x0C, the type 1 slot at +0x20 and the type 2 slot at +0x30, a slot used only if its address is not 0xFFFFFFFF and address OR check is 0xFFFFFFFF, record first byte last; a record with a blank type 2 slot and a valid type 1 slot starts section B | §5, §6 (Simulated on the stock boot section) | The net does not arm (the selector still starts this image) or, worse, a record the selector dislikes makes it scan, which still finds section B first |
| H11 | A record-only update may copy 0x400–0xFFFF verbatim and the stock programs accept the block; the record's halfword pairs at +0x10/+0x14 and the +0x18–0x1F bytes need no change | §5 (Observed; meaning of the halfwords unknown) | The stock application may compact or rewrite the store on its next start; nothing is lost that it cannot rebuild |
| H12 | The stock installer writes a type 2 slot pointing at the new section's table entry, in both blocks, and restarts (Q10: not reproduced end to end on the board model) | §7.2, Q10 | The image is in flash but never started, or started by the scan; power-cycling may help |
| H13 | The image version 9.0.1 is above the per-model floor and the provider minimum | §7.2 | The web upgrade is refused; nothing happens |
| H14 | Section B at 0x20000 is intact and at a 64 KB boundary, and the type 1 slot points at it | §5, flash.md §2 | No recovery through the net; the selector stops at step 5 |
| H15 | The Am29LV081B's command set and status bits as the datasheet says apply to this part on this board (A10–A0 or none of the address bits decoded for commands; DQ5 on failure) | Datasheet; flash.md §1 (the stock driver uses the same commands) | Flash failure patterns, or in the worst case a sector erased and not rewritten (the record's first byte last protects the selector's view) |

## 9. What the specs do not say (questions for the spec)

Gaps met while writing this. Where a choice had to be made, the choice
is given; none of them is guessed into the flash contents.

| # | Question | What this image does meanwhile |
|---|---|---|
| G1 | The boot selector's choice when both blocks hold the same sequence number (format spec §5: "not known") | Takes block 1 as active, as sections A and B do; after its first write there is no tie |
| G2 | Does the selector check anything in the record beyond `SIPURA *` and the sequence number (the +0x0C complement, the +0x10/+0x14 pairs, the slot magic)? Section A checks all four pairs | Copies every byte it does not have to change, so the record is as valid as the one found |
| G3 | On a record-only update by the stock programs, is the event log (0x800–0xFFF) copied, and is the header copy at +0x400 rewritten from the record's own header or from the image? ("copies 0x1000–0xFFFF ... then writes the header copy and the record") | Copies 0x400–0xFFFF verbatim |
| G4 | What "marks that block as active" means in the stock programs: a RAM flag, or something in flash? | Nothing in flash; the next reader compares sequence numbers |
| G5 | The exact content of the slot-less record the stock application writes on blank boot sectors: are the slots all 0xFF, and is the type 1 slot kept? | Blanks the 16 bytes of the type 2 slot only; keeps the type 1 slot |
| G6 | Whether the stock application, when it next runs, accepts a boot record it did not write (sequence number +2, same content) without compacting the store or logging an error | Nothing; worth watching on the way back to stock firmware |
| G7 | The watchdog's time-out and whether it runs from reset (P1) | §7 |
| G8 | What 0x20004028 does (P2) and whether the values 0 and 9 matter | Writes them as the stock firmware does |
| G9 | Port 0's direction and data latch at hand-over from the boot selector; whether the boot code touched the system-control device beyond using the same address | Drives only bit 3 |
| G10 | Whether the timer at 0x2000400C runs without the interrupt controller being set up (§7.3 step 14) and what 0x4008 = 0xFF and 0x4014 = 0 do | Writes them as the stock firmware does; detects a stuck timer |
| G11 | Whether reads through 0x0C000000 are cached (the address bit 28 hypothesis) and whether the flash driver must use 0x1C000000 | Uses 0x1C000000 for every flash access, as the stock driver does |
| G12 | The loader stub's entry conditions beyond the stub's own assumptions (`tools/README.md`): PSW, cache state, what else the selector expects of a section | Nothing to do; H1 |
| G13 | Whether the 0x1C000000 alias and the chip's 1 MB repeating through the window are real (format spec Q6) | Masks slot addresses to 20 bits before reading them |
| G14 | The per-model version floor and the provider's minimum version (§7.2) | Version 9.0.1 |
| G15 | What the stock installer writes at 0x400 of the boot blocks for a one-section image (the header is 0x80 bytes; "then 0xFF to the end of the area") and whether section B's version reader (+0x400 + 0x5C) is happy with it | Copies it |
| G16 | flash.md: the stock driver "verifies every sector erase by reading the sector back, retries erases and byte programs, and kicks the watchdog inside its erase and program loops"; how many retries, and what it does when they run out | 3 attempts each; on failure the active block is left untouched and the LEDs blink fast |

Notes for the dirty side, if the specs are revised: format spec §6 step
3 still says "compute the MD5 over 0x000–0x1FF", which §2 and step 4
contradict (also in `packer-layout-handover` notes). flash.md §1 says
the firmware's 0x5555/0x2AAA unlock addresses work because "only A10–A0
are decoded"; the Rev D datasheet (Table 4 note 4) says all address bits
are don't-cares for unlock and command cycles on this part.
