# mipsx-sdk

Tools and runtime for writing new firmware for the ES3890, the MIPS-X
derived CPU in the Linksys (Sipura) SPA3000. It works with the LLVM fork
on branch `mipsx` (experimental target `MIPSX`).

Planned contents:

| Path | What |
|---|---|
| `docs/abi.md` | The ABI: registers, calls, stack, assembler syntax, ELF flags and relocations |
| `sim/` | Instruction-set simulator that loads an ELF and reports pipeline hazards |
| `crt0/` | Start-up code and linker scripts for the simulator and the device |
| `packer/` | Turns a linked ELF into an SPA3000 upgrade image |

This is clean-room work: it is written from public documentation and
from specifications that contain facts only, never from the vendor's
firmware.

Licensed under the Apache License 2.0; see [`LICENSE`](LICENSE).
