# rt: start-up code and linker scripts

Work package S7 of the LLVM backend plan. Implements `docs/abi.md` §13.

| File | What |
|---|---|
| `crt0.S` | `_start`: sp, r23/r24 code bases, gp, `.data` copy (if its load address differs), `.bss` clear, `__init_array`, then `exit(main(0, 0))` (abi §13.3) |
| `exit-sim.S` | `_exit` (and weak `exit`) for the simulator: stores the status to the I/O page exit register (abi §13.5) |
| `exit-device.S` | `_exit` (and weak `exit`) for the device: stops in a loop (how to reset the ES3890 is not known yet) |
| `sim.ld` | Linker script for `mipsx-sim` |
| `device.ld` | Linker script for the SPA3000; its output goes to `tools/mipsx_pack.py` |
| `tests/` | `crt0_main.s` (checks what crt0 set up, prints, returns 42) and `test_rt.py` |

Linking, once lld supports MIPS-X (S5):

```
llvm-mc -triple=mipsx -filetype=obj crt0.S -o crt0.o      # likewise exit-*.S
ld.lld -T rt/sim.ld crt0.o exit-sim.o prog.o -o prog
sim/build/mipsx-sim prog
```

`crt0.S` and the exit files need no C preprocessor; the simulator and
device builds differ only in which exit file is linked. Both `exit`
definitions are weak so that a C library's `exit` (S15) takes over and
calls our `_exit`.

## Memory map (both scripts)

| Address | Content |
|---|---|
| 0x000000–0x001FFF | `.vectors` if a program has one (address 0 is the exception entry, trap n at n × 32). The device loader stub briefly uses 0x1FF0–0x1FFB |
| 0x002000 | `.text` (crt0's `.text.start` first), `.rodata`, `.init_array`, `.data`, `.sdata`, `.sbss`, `.bss` |
| `__stack_top` = 0x1FFFF0 | Initial sp, growing down; the scripts assert at least 64 KB between `_end` and it |

`__mipsx_cb0` = `.text` + 0x40000, `__mipsx_cb1` = cb0 + 0x80000, `_gp` =
`.sdata` (or `.data` if `.sdata` is empty) + 0x10000, as abi §13.1.
`.data` is not given a separate load address: the simulator and the
device loader both put every segment at its load address in RAM, so
`__data_load` = `__data_start` and crt0 skips the copy. The copy path is
still tested by moving `.data` (mxasm `--data-vma`).

## Status

- `crt0.S` runs on the simulator with no hazard reports, assembled and
  laid out by `sim/tests/mxasm.py` (`make check` at the top level).
- **The linker scripts are not link-tested**: lld does not support MIPS-X
  until S5. `mxasm.link_layout()` mirrors `sim.ld` for the tests; when S5
  lands, link `tests/crt0_main.s` with lld and both scripts, compare the
  symbol values with `link_layout()`, and run the result. Points to check
  then: lld must not put the ELF headers in a PT_LOAD (it should not,
  since nothing is free below 0x2000 at page alignment), `SIZEOF(.sdata)`
  in the `_gp` expression with an empty `.sdata`, and `NOLOAD` `.sbss`.
- Overflow traps: crt0 does not touch PSW, because the ES3890's PSW
  layout is unconfirmed (abi §2.3, §13.3).
