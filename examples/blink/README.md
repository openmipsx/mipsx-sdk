# examples/blink: the first SPA3000 image

Step 2 of the open-source stack plan (§4): an image that the stock boot
section loads, which blinks the status LEDs. It also kicks the watchdog,
and it carries a **dead-man net** so that a unit on which it hangs still
reaches the stock recovery program. Written from the specifications in
openmipsx/devices (`spa3000/peripherals.md`, `spa3000/flash.md`,
`common/firmware-image-format.md`, `common/processor-es3890.md`) and
the Am29LV081B datasheet; no vendor code.

**Status: never run on the board.** Both variants build, pack, pass
`tools/mipsx_verify.py`, and run on the simulator: on the program's own
peripheral model and, as packed images started from flash, on the
simulator's SPA3000 board model (§6). Every fact the image depends on
that the specs mark Hypothesis is listed in §8, and the questions this
image put to the specs in §9, each with what the specs (devices
`8320838` and later) now answer and what is still open. Read both
before flashing.

| File | What |
|---|---|
| `main.c` | Start-up order and the blink loop |
| `board.c`, `board_io.h` | Watchdog kick, system-control port, port 0 LEDs, timer |
| `flash.c`, `flash.h` | Am29LV081B driver (identify, sector erase, byte program) |
| `bootrec.c`, `bootrec.h` | Boot record reading and the dead-man net |
| `board.h`, `hal.h`, `util.*` | Addresses from the specs; the volatile accesses; `memcpy` and friends |
| `vectors.S` | A no-op and a jump to a stop loop at address 0 |
| `sim/model.c` | Timer, system-control and flash models for the simulator build, and the boot selector's view of the records |
| `tests/test_blink.py` | Image, loader stub, model and board-model tests (`make check`) |

## 1. Building

```
cd examples/blink
make MIPSX_LLVM_BIN=/path/to/llvm-project/build/bin SYSROOT=/path/to/mipsx-sdk/build/sysroot
make check MIPSX_LLVM_BIN=... SYSROOT=...     # needs sim/build/mipsx-sim
```

`make check` takes about 45 s, most of it one 16.5 s run on the board
model (§6).

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
   toggle (every 0.5 s, well inside the 2–3 s the spec asks for) and
   inside the flash driver's polling loops. (The stock driver does not
   kick: its installers turn the watchdog off for the install instead,
   flash.md §1, peripherals.md §5.)
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
| Toggling every 1 s | Net skipped: no boot record, the type 2 slot of the record the selector follows unused, the slot's section is not this program, the sequence number too close to 0xFFFFFFFF, or the flash did not identify as an Am29LV081B (nothing was written) |
| Toggling every 0.125 s | A flash erase (3 attempts) or byte program (9 attempts) failed; the active block is untouched |
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

**Which block is active.** The one the boot selector follows, since
the selector is the program the net has to steer (§5 "What each
program checks in a record"): it checks only the 8-byte magic of each
block; with both valid it takes the higher +0x08 word, compared
**unsigned**, and **block 0 on a tie**. Sections A and B choose
differently (a valid type 2 slot first, then the other flags, then a
signed compare, block 1 on a tie), and the image must not copy them:
on a tie in which only block 0 has a type 2 slot, the selector starts
this image from block 0, and taking block 1 would leave the net off.

Each write does what sections A and B do (§5 "Boot-record blocks"):
erase the inactive block; copy the active block's 0x400–0xFFFF across
unchanged (the image-header copy, the event log, the configuration
store and its mirror; the installers write the newest 16 log entries
and the image's header instead, and §6 says a verbatim copy is fine,
since the stock programs rewrite both the next time they rewrite a
block); write the record with its first byte last, so that a block
with an incomplete `SIPURA *` is never taken as valid; read everything
back. The record written is the record found with the sequence number,
its complement, the type 2 slot and the halfword pairs at +0x10 to
+0x17 rewritten. The pairs get `04 00 FB FF 10 00 EF FF`, the bytes both
installers write (§5), so the restored record passes all six of the
stock application's checks even if the record found did not (the
selector does not read them; §6: otherwise the application compacts
once). The type 1 slot, bytes +0x18 to +0x1F and any further slots are
copied (§6: keep the type 1 slot).

Before writing anything the image checks, in order, and otherwise
leaves the flash alone (the 1 s blink):

- the chip answers the autoselect command with 01h / 38h (Am29LV081B);
- one of the two blocks holds `SIPURA *`; with both valid the higher
  sequence number, unsigned, wins, and block 0 on a tie, as the boot
  selector chooses (§5);
- the type 2 slot of that record is usable (address not 0xFFFFFFFF,
  address OR check = 0xFFFFFFFF, §5);
- its sequence number is below 0xFFFFFFFE, so that seq + 1 and then
  seq + 2 each beat the record before them in the selector's unsigned
  compare (with seq + 2 wrapped to 0 the restore would lose to the armed
  record, and every reset would start section B);
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

**When the stock firmware comes back** (§5, §6; Simulated there).
Section B, started by the armed record, writes nothing to the blocks, so
repeated resets keep landing in B. Reinstalling the stock image from
section B rewrites both blocks. Should the stock application ever start
on blocks the net wrote, it accepts the restored record (magic,
complement, pairs and type 2 slot right); a block without a type 2
slot, such as an armed record, makes it rewrite that block from the
other at start-up, which costs one compaction and logs nothing.

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
   section MD5, turns the watchdog off (peripherals.md §5), writes the
   section to flash 0xE0000, writes a boot record with the type 2 slot
   pointing at it to both blocks (the block active before the install
   gets the higher number), turns the watchdog back on, logs the version
   and restarts (§5, §7.2). Q10 of the format spec: on the board model
   the installer wrote the section where expected but what it did next
   could not be reproduced, so the install-then-boot path is unverified
   end to end. The boot selector does start a section left as §5
   describes (Simulated), and this image does on the simulator's board
   model (§6).

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
Section B writes nothing to the boot blocks, so it is started again on
every reset until something is installed (§6, Simulated).
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
  program laid out as the packer lays a section out. The model also
  prints the boot selector's view of the blocks (format spec §5: magic
  only, higher sequence number unsigned, block 0 on a tie, then the
  type 2 slot, then the type 1 slot) at the start and after every flash
  operation that changes it, so the tests check that the selector
  follows this program, then section B, then this program again. The
  tests check the net end to end (armed into the inactive block,
  restored into the other, sequence numbers and complements, the
  installers' halfword pairs, the 0x400–0xFFFF copy, the LED period,
  data written before direction), including a tie (block 0 active), a
  tie where only block 0 has a type 2 slot, a sequence number above
  0x7FFFFFFF (unsigned compare) and a record with a wrong complement and
  zeroed pairs; and every reason to leave the flash alone: no record, a
  newer block 1 without a type 2 slot (which the selector follows and
  the stock application would not), the type 2 slot unused, a sequence
  number that would wrap, a section that is not this program, a chip
  with the wrong ID, a stuck timer, and erase and program failures (DQ5;
  3 erase attempts, 9 program attempts).
- `blink.bin` and `blink-wd.bin` themselves run on the simulator's
  SPA3000 board model (`mipsx-sim --board=spa3000`, `sim/README.md`
  "Board model"), which was written separately from `sim/model.c`. The
  test builds a 1 MB flash file with two boot records and the image's
  section at 0xE0000, and starts the run at data + field 0x14 in flash,
  where the selector jumps (§5 "Order" step 4). With equal sequence
  numbers the image erases block 1 (block 0 is active) before the LEDs
  start, and the LEDs toggle every 0.5 s. `blink-wd.bin`, with the
  board's watchdog set to 2 s, runs 16.5 s: arm into block 1, enable
  the watchdog, blink, restore into block 0 at 15 s and blink on, with
  no bite. The board model's flash does not write back to the file, so
  record contents are checked on `sim/model.c` only.

## 7. The watchdog question (peripherals.md P1)

Variant 1 never sets reg 3 bit 7; variant 2 sets it after kicking has
started. Both kick. Readings:

- Variant 1 resets on its own: the watchdog runs from reset and the
  kick does not satisfy it (or something else resets the chip).
- Variant 1 steady, variant 2 resets every T seconds: the kick is
  wrong and T is the time-out, or longer than T is needed.
- Both steady: the kick works; whether the watchdog runs from reset is
  still open. (The stock installers turn bit 7 off and on again around
  an install, peripherals.md §5, so the bit is a run-time switch, not a
  one-time enable.) Build with `-DBLINK_KICK_STOP_S=60`: 60 s after the
  restore the image stops kicking while it goes on blinking. The time
  from then to the restart (LEDs dark, then the pattern starts over) is
  the time-out; no restart within minutes means the watchdog is off in
  that variant. The restart goes through the boot code and starts this
  image again (the record was restored), so this is safe to try.

## 8. Hypotheses this image depends on

Each is a fact the specs mark Hypothesis (or that only the stock
firmware's behaviour supports), with what the specs say now and what
happens here if it is wrong. "Format spec" is
`common/firmware-image-format.md`; § numbers without a file are
`spa3000/peripherals.md`.

| # | Fact | Spec now | If wrong |
|---|---|---|---|
| H1 | The boot selector starts the type 2 slot's section by jumping to data + length − 0x10, with the loader stub's entry conditions (RAM at 0x1FF0 free, code runnable from freshly written RAM, nothing else expected of the section) | **Mostly answered.** Format spec §5 "Order" step 4 (Verified for the stock stubs; the selector starting an installed section is Simulated, Q10); up to the jump the selector touches no register, port or device (§5, Observed and Simulated). The image's start must be a multiple of 4 (§6), which `mipsx_verify.py` checks. On the board: unverified | Nothing blinks; the selector stops or runs garbage. Recovery needs a flash programmer unless the selector falls back |
| H2 | Interrupts are masked at hand-over, or masking them with PSW bit 4 (the manual's M bit) works; exceptions enter at word 0 | **Mostly answered.** PSW bit 4 is the mask (processor spec §10); the reset code sets PSW = 0xF3, bit 4 included, before anything else (§7.1), and the selector does nothing that would clear it. What exceptions other than `trap` do is still not known (processor spec §10) | A stray interrupt or exception goes to address 0 and stops (variant 2: resets) |
| H3 | 0x2000400C counts up once per CPU cycle, at 81 MHz, without an interrupt enabled and after only the §7.2 step 7 writes | Unchanged: §4, Hypothesis, strong; G10 | Period other than 0.5 s, or the fallback loop's rate |
| H4 | The watchdog kick is the low-then-high pulse on 0x2000402C bit 2; its time-out exceeds 0.5 s; it is off from reset (or on, and the kick satisfies it) | **Partly.** Kick and enable still Hypothesis, strong (§5). New: the installers turn reg 3 bit 7 off and on again around an install (§5, Observed), so it is a run-time switch. Time-out and state at reset open (P1) | Variant 1 resets (watchdog on from reset and kick wrong), or variant 2 resets at the time-out |
| H5 | Port 0 of the system-control device works with none of the stock firmware's other system-control writes (regs 0, 1, 2, 0x22, 0x23, 0x40, 0x43, 0x46, 0x47, 0x63, 0x64, 0x70) and none of the §7.2 step 3–6 on-chip writes; the CPU runs at 81 MHz without the reg 0x43/0x46/0x47 PLL values | Unchanged: §3, §7.2 step 11 (roles unknown; P4) | LEDs dark (port 0 not reached) or wrong rate (clock) |
| H6 | The two-step byte protocol at 0x14000003 (address byte reg << 1 \| rw, then data), with 0x20004028 = 0 before each access, and address bits 1–0 not decoded | **Partly.** Protocol unchanged (§3, Observed). 0x20004028 is now read as the interrupt-suppress register (§2, §4; Hypothesis, strong): 0 holds interrupts off for 15 instructions, 9 for 6. With interrupts masked throughout, the image's writes to it change nothing; they are kept as the stock firmware makes them | LEDs dark |
| H7 | Port 0 bit 3 (AUX1[3], pin 111) drives D4, D7, D8 through Q21 as a high-side switch: driven 0 = on, driven 1 = off; data then direction is the right order | Unchanged: §6 (pin Measured; polarity fits hardware.md H4) | LEDs inverted or dark |
| H8 | Port 0's other bits are released before the first write and may stay released (Ethernet, SLIC and DAA resets, Si3050 CS#) | **Partly.** Neither the reset code nor the selector touches port 0, so the image finds it as the hardware reset left it (format spec §5 "Order"; §7.1). That the reset state is all released is still Hypothesis (§6) | Nothing for the LEDs; the other chips are in whatever state reset left them |
| H9 | The flash is an Am29LV081B at 0x0C000000, byte-wide, with the CPU's byte address n reaching flash byte n, commands and reads working through the 0x1C000000 alias (the form the stock driver uses), and WE# wired so the CPU can write | Unchanged: flash.md §1; the stock code relies on both aliases (format spec Q6) | Identify fails (1 s blink, flash untouched), or writes fail (0.125 s blink) |
| H10 | The boot record format of format spec §5: `SIPURA *`, sequence at +0x08, the type 1 slot at +0x20 and the type 2 slot at +0x30, a slot used only if its magic is there, its address is not 0xFFFFFFFF and address OR check is 0xFFFFFFFF; a record with a blank type 2 slot and a valid type 1 slot starts section B | **Answered** (format spec §5 "What each program checks in a record", "Order"; Observed in the selector's code, Simulated). The selector checks only the magic, compares sequence numbers unsigned and takes block 0 on a tie; the image now chooses the same way (it took block 1 on a tie before) | — |
| H11 | A record-only update may copy 0x400–0xFFFF verbatim and the stock programs accept the block; the record's halfword pairs need no change | **Answered** (format spec §6 "Rewriting the boot record from our own code"): verbatim log and header copy are fine; the application accepts a record whose magic, complement, both pairs and type 2 slot are right, and otherwise compacts once. The image now writes the installers' pair values rather than copying them. The pairs' meaning is still open (Q6) | — |
| H12 | The stock installer writes a type 2 slot pointing at the new section's table entry, in both blocks, and restarts | **Open**: format spec §5, §7.2 describe it (Observed in the code), but Q10 (not reproduced end to end on the board model) stands | The image is in flash but never started, or started by the scan; power-cycling may help |
| H13 | The image version 9.0.1 is above the per-model floor and the provider minimum | **Open** (format spec §7.2: the floor's value is not given) | The web upgrade is refused; nothing happens |
| H14 | Section B at 0x20000 is intact and at a 64 KB boundary, and the type 1 slot points at it | Unchanged; a property of the unit, which no spec can settle (format spec §5, §6; flash.md §2, §6) | No recovery through the net; the selector stops at step 5 |
| H15 | The Am29LV081B's command set and status bits as the datasheet says apply to this part on this board (DQ5 on failure) | **Answered** for the commands: flash.md §1 now agrees with the datasheet that unlock and command addresses are don't-cares, and gives the stock driver's retry counts (G16) | Flash failure patterns, or in the worst case a sector erased and not rewritten (the record's first byte last protects the selector's view) |

## 9. Questions this image put to the specs

The questions met while writing this, and what the specs (devices
commit `8320838`, which names G1–G6, G9, G15 and G16 as answered, and
`55c7c7d` for 0x20004028) now say. None of the answers is guessed into
the flash contents.

**Answered**

| # | Question | Answer | What the image does now |
|---|---|---|---|
| G1 | The boot selector's choice when both blocks hold the same sequence number | Block 0 (format spec §5 "What each program checks in a record"; Simulated). Sections A and B take block 1 | **Changed**: takes block 0 on a tie, as the selector does (it took block 1). Tests: `test_tie`, `test_tie_block1_slotless`, `test_tie_arms_from_block0` |
| G2 | Does the selector check anything in the record beyond `SIPURA *` and the sequence number? | No: only the block magic, then the slot it uses (magic, address, address OR check) and the section. The +0x0C complement, the +0x10/+0x14 pairs and +0x18 to +0x1F are not read. The sequence compare is unsigned. Sections A and B check six flags (§5) | **Changed**: writes the right complement and the installers' pair bytes even when the record found has neither, so the restored record passes the application's checks too; the sequence compare is unsigned, and a sequence number of 0xFFFFFFFE or more leaves the flash alone. Tests: `test_odd_record`, `test_seq_unsigned`, `test_seq_wrap` |
| G3 | On a record-only update by the stock programs, is the event log copied, and is the header copy rewritten? | Installs write the newest 16 log entries into slots 0–15 and the image's header (then 0xFF) at +0x400; a compaction copies the first 0x80 bytes of the header copy. §6: a verbatim copy of both is fine | No change: copies 0x400–0xFFFF verbatim |
| G4 | What "marks that block as active" means in the stock programs | A variable in RAM; nothing in flash (§5) | No change |
| G5 | The exact content of the slot-less record the stock application writes on blank boot sectors | Sequence 0, complement 0xFFFFFFFF, the usual pairs, and 0xFF from +0x18 to +0x9F: every slot erased, type 1 included (§5) | No change: such a record has no type 2 slot, so the image leaves the flash alone. Its own armed record keeps the type 1 slot, as §6 advises |
| G6 | Does the stock application accept a boot record it did not write? | Yes, if magic, complement, both pairs and the type 2 slot are right; otherwise it rewrites the other block at start-up and logs nothing (§5, §6; Simulated) | See G2. An armed record (no type 2 slot) would cost one compaction, but while it is the newer record the selector starts section B, not the application |
| G9 | Port 0's state at hand-over from the boot selector; does the boot code touch the system-control device? | Nothing before the jump touches any register, port or device (format spec §5 "Order"; §7.1), so port 0 is as the hardware reset left it. Its reset state is still Hypothesis (§6: presumably all released) | No change: drives only bit 3 |
| G15 | What the stock installer writes at 0x400 of the boot blocks for a one-section image, and is section B's version reader happy with it? | The image's header-size bytes (its 0x80-byte global header), then 0xFF to +0x57F. Section B reads only the version string at +0x45C, and uses a built-in one if that byte is 0xFF (§5 "Boot-record blocks") | No change: copies it |
| G16 | The stock driver's retries, and what it does when they run out | Section A: 9 attempts per byte, 3 per sector erase (B: 61 and 5); a byte already right is skipped; each operation ends with a reset command. The record writers ignore failures and carry on; the installer repeats failed section writes without limit (flash.md §1) | **Changed**: 9 program attempts per byte (it made 3); erase attempts stay at 3. On failure it still stops and leaves the active block alone, which is stricter than the stock record writers. Test: `test_program_fail` |

**Partly answered**

| # | Question | What the specs say | What the image does |
|---|---|---|---|
| G8 | What 0x20004028 does (P2), and whether the values 0 and 9 matter | Interrupt suppress: writing S holds interrupts off for the next 15 − S instructions (§2, §4; Hypothesis, strong, from a public account of the predecessor chip). peripherals.md §10 still lists P2 as open | Writes 9 before each kick and 0 before each system-control access, as the stock firmware does. With interrupts masked for the whole run, they change nothing |
| G12 | The loader stub's entry conditions: PSW, cache state, what else the selector expects of a section | The selector touches nothing but flash and RAM before the jump (format spec §5); the reset code sets PSW = 0xF3 (§7.1); the selector checks type, entry sum, length, MD5 and the start's alignment, and the tag only on a scan (§5 "Section check", §6). Cache state not described | Nothing to do; H1 |

**Still open**

| # | Question | Where it stands | What the image does meanwhile |
|---|---|---|---|
| G7 | The watchdog's time-out and whether it runs from reset (P1) | Open (peripherals.md §5, §10). The installers turning bit 7 off and on is new (§5) | §7 |
| G10 | Whether the timer at 0x2000400C runs without the interrupt controller being set up, and what 0x4008 = 0xFF and 0x4014 = 0 do | Open (clean-room log for `8320838`: "G10 and G13 remain open"). §4 also notes the firmware writes 0x4014 once, with 0, at reset; its role is unresolved | Writes them as the stock firmware does; detects a stuck timer |
| G11 | Whether reads through 0x0C000000 are cached (the address bit 28 hypothesis) and whether the flash driver must use 0x1C000000 | Open (peripherals.md §1: Hypothesis) | Uses 0x1C000000 for every flash access, as the stock driver does |
| G13 | Whether the 0x1C000000 alias and the chip's 1 MB repeating through the window are real | Open (format spec Q6; the stock code relies on both aliases) | Masks slot addresses to 20 bits before reading them |
| G14 | The per-model version floor and the provider's minimum version | Open (format spec §7.2) | Version 9.0.1 |

The two spec errors this README used to point out are fixed on the
devices side: format spec §6 step 3 now gives the installers' MD5 range
(`e4fb8ed`), and flash.md §1 now says the unlock and command addresses
are don't-cares on this part (`8320838`).

**Before flashing**, the facts above that only the board can settle
are H3–H9 (the timer, watchdog, system-control port, LED wiring and
flash wiring), H12 (the stock installer's install-then-restart, Q10),
H13 (the version floor) and H14 (section B intact on this unit). The
net covers a hang after arming; nothing covers an image that is never
started, or that stops before stage 3 (§3, "What each failure leads
to").
