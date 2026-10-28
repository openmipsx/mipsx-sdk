# mipsx-sdk

Tools and runtime for writing new firmware for the ES3890, the MIPS-X
derived CPU in the Linksys (Sipura) SPA3000. It works with the LLVM fork
on branch `mipsx` (experimental target `MIPSX`).

Contents:

| Path | What |
|---|---|
| `docs/abi.md` | The ABI: registers, calls, stack, assembler syntax, ELF flags and relocations |
| `sim/` | Instruction-set simulator that loads an ELF and reports pipeline hazards |
| `rt/` | Start-up code (`crt0.S`) and linker scripts for the simulator and the device |
| `tools/` | `mipsx_pack.py` turns a linked ELF into an SPA3000 upgrade image; `mipsx_verify.py` checks one |

`make` builds the simulator; `make check` runs the simulator, crt0 and
packer tests (needs a C compiler and python3).

## Simulator

`sim/` builds with `make -C sim` and tests with `make -C sim check`.
`sim/build/mipsx-sim prog.elf` runs a linked program: stdout and stdin
go through the I/O page of `docs/abi.md` §13.5, the exit status is the
program's, and pipeline hazards (abi §9) stop it with status 125.
`sim/mipsx-run` wraps it for lit (`--expect-exit=N`, `--print-exit`).
See [`sim/README.md`](sim/README.md).

## Start-up code and image packer

`rt/crt0.S` starts a program as `docs/abi.md` §13.3 says; `rt/sim.ld` and
`rt/device.ld` lay it out (not link-tested until lld supports MIPS-X).
`tools/mipsx_pack.py prog.elf -o prog.bin` makes an upgrade image with
one type 2 section and a position-independent loader stub;
`tools/mipsx_verify.py prog.bin` checks an image against the format
spec. See [`rt/README.md`](rt/README.md) and
[`tools/README.md`](tools/README.md), which lists what to confirm before
flashing anything.

This is clean-room work: it is written from public documentation and
from specifications that contain facts only, never from the vendor's
firmware.

Licensed under the Apache License 2.0; see [`LICENSE`](LICENSE).
