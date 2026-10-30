# rt: start-up code and linker scripts

Work package S7 of the LLVM backend plan. Implements `docs/abi.md` §13.

| File | What |
|---|---|
| `crt0.S` | `_start`: sp, r23/r24 code bases, gp, `.data` copy (if its load address differs), `.bss` clear, `__init_array`, then the argv block from the board's hooks and `exit(main(argc, argv))` (abi §13.3) |
| `exit-sim.S` | `_exit` (and weak `exit`) for the simulator: stores the status to the I/O page exit register (abi §13.5) |
| `args-sim.S` | `__mipsx_args_size` and `__mipsx_args` for the simulator: the command line, through the I/O page (abi §13.3, §13.5) |
| `args-device.S` | The same for the device: no command line, so `argc` 0 and `argv` = `{ NULL }` |
| `exit-device.S` | `_exit` (and weak `exit`) for the device: stops in a loop (how to reset the ES3890 is not known yet) |
| `sim.ld` | Linker script for `mipsx-sim` |
| `device.ld` | Linker script for the SPA3000; its output goes to `tools/mipsx_pack.py` |
| `builtins/` | Multiply, divide and variable-shift helpers for the code generator (`__mulsi3`, `__divdi3`, `__ashldi3`, ...); see `builtins/README.md` |
| `tests/` | `crt0_main.s` (checks what crt0 set up, prints, returns 42) and `test_rt.py`; `test_builtins.py` checks the helpers against a Python reference |

Linking with the LLVM tools:

```
llvm-mc -triple=mipsx -filetype=obj crt0.S -o crt0.o      # likewise exit-*.S, args-*.S
ld.lld -T rt/sim.ld crt0.o exit-sim.o args-sim.o prog.o -o prog
sim/build/mipsx-sim prog
```

`crt0.S`, the exit files and the args files need no C preprocessor; the
simulator and device builds differ only in which exit and args files are
linked (`libsim.a` or `libdevice.a`). Both `exit` definitions are weak
so that a C library's `exit` (S15) takes over and calls our `_exit`.

## Memory map (both scripts)

| Address | Content |
|---|---|
| 0x000000–0x001FFF | `.vectors` if a program has one (address 0 is the exception entry, trap n at n × 32). The device loader stub briefly uses 0x1FF0–0x1FFB |
| 0x002000 | `.text` (crt0's `.text.start` first), `.rodata`, `.init_array`, `.fini_array`, `.data`, `.sdata`, `.sbss`, `.bss` |
| `_end` to `__stack_top` − 64 KB | The C library's heap (`__heap_start`, `__heap_end`) |
| `__stack_top` = 0x1FFFF0 | Initial sp, growing down; the scripts assert at least 64 KB between `_end` and it |

`__mipsx_cb0` = `.text` + 0x40000, `__mipsx_cb1` = cb0 + 0x80000, `_gp` =
`.sdata` (or `.data` if `.sdata` is empty) + 0x10000, as abi §13.1.
`.fini_array` holds destructors and picolibc's `.fini_array_onexit`
(its `atexit` runner), which `exit` runs.

`.data` is not given a separate load address: the simulator and the
device loader both put every segment at its load address in RAM, so
`__data_load` = `__data_start` and crt0 skips the copy. The copy path is
still tested by moving `.data` (mxasm `--data-vma`).

## Status

- `crt0.S` runs on the simulator with no hazard reports, assembled and
  laid out by `sim/tests/mxasm.py` (`make check` at the top level).
- Both linker scripts link with ld.lld (`make check-llvm
  MIPSX_LLVM_BIN=.../llvm-project/build/bin`, `tests/test_llvm.py`):
  crt0, the exit routines and `tests/crt0_main.s` are assembled with
  llvm-mc, and every section address and abi §13.1 symbol matches
  `mxasm.link_layout()`, with and without `.sdata`/`.sbss` contents. The
  simulator build runs (42, no hazards); the device build packs and passes
  `tools/mipsx_verify.py`. lld puts no ELF headers in a PT_LOAD, and
  `NOLOAD` `.sbss` and the `SIZEOF(.sdata)` test in `_gp` work. The
  helpers in `builtins/` assemble with llvm-mc. The other `rt/` tests
  still link with `mxasm.link_layout()`.
- Overflow traps: crt0 does not touch PSW, because the ES3890's PSW
  layout is unconfirmed (abi §2.3, §13.3).
