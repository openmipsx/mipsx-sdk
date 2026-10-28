# mipsx-sim: MIPS-X (ES3890) instruction-set simulator

Runs a linked MIPS-X ELF executable and reports every violation of the
pipeline rules in [`../docs/abi.md`](../docs/abi.md) §9 that it sees,
instead of silently computing a wrong answer. Written from the processor
spec (`linksys-spa3000/docs/spec/processor-es3890.md`), the ABI and the
public MIPS-X manual. Work package S6 of the LLVM backend plan.

## Building and testing

```
make            # builds build/mipsx-sim (any C11 compiler)
make check      # runs the tests (needs python3)
make install PREFIX=...   # installs mipsx-sim and mipsx-run into PREFIX/bin
```

## Running

```
mipsx-sim [options] program.elf
```

| Option | Meaning |
|---|---|
| `-t`, `--trace` | Trace every instruction to stderr: cycle, byte address, word, disassembly, effect (register written, memory address, branch outcome, squashed slots) |
| `--trace-file=FILE` | Trace to FILE |
| `-c N`, `--max-cycles=N` | Stop after N cycles with status 124 (default 10⁹; 0 = no limit) |
| `--hazards=error\|warn\|off` | What a pipeline rule violation does (default `error`) |
| `-w`, `--warn-hazards` | Same as `--hazards=warn` |
| `-m N`, `--mem-size=N` | Size of RAM at address 0 (default 0x200000, the device's 2 MB) |
| `-s`, `--stats` | At exit, print cycles, instructions, squashed slots, store stalls and delay-slot use (how many slots hold `nop`; for S11) |
| `-d`, `--disassemble` | Print the disassembly of the executable segments and exit |

Exit status: the program's exit status (the low 8 bits of the word
stored to the exit register), or

| Status | Meaning |
|---|---|
| 124 | Cycle limit reached |
| 125 | Simulation error: pipeline hazard (in `error` mode), undefined instruction, access to unmapped memory, fetch outside RAM, `hsc` |
| 126 | The program could not be loaded, or bad options |

Diagnostics go to stderr, prefixed `mipsx-sim: error:` or `warning:`,
with the PC as a byte address and the nearest symbol, for example:

```
mipsx-sim: error: pc 0x00002008 <_start+0x8>: load-use hazard (P1): mov r4,r5 reads r4, loaded by the previous instruction at 0x00002004 <_start+0x4> (cycle 3)
```

## The runner, `mipsx-run`

For lit and other harnesses. It finds the simulator (`$MIPSX_SIM`, else
`mipsx-sim` next to the script, else `build/mipsx-sim` next to it, else
`PATH`), passes all other options to it, and adds:

| Option | Meaning |
|---|---|
| `--expect-exit=N` | Exit 0 if the program's status is N, else print a message and exit 1 |
| `--print-exit` | After the run, print `exit: N` on stdout, for FileCheck |

`$MIPSX_RUN_MAX_CYCLES`, if set, becomes `--max-cycles` (an explicit
option wins). Without `--expect-exit` the status is the simulator's.

A lit configuration in the LLVM tree (not written yet; S8) would add a
substitution and use it like this:

```
# lit.local.cfg (sketch): MIPSX_SDK points at a built mipsx-sdk checkout
import os
sdk = os.environ.get("MIPSX_SDK")
run = sdk and os.path.join(sdk, "sim", "mipsx-run")
if not run or not os.path.exists(os.path.join(sdk, "sim", "build", "mipsx-sim")):
    config.unsupported = True
else:
    config.substitutions.append(("%mipsx-run", run))
```

```
; RUN: llc -mtriple=mipsx -filetype=obj %s -o %t.o
; RUN: ld.lld -T %S/Inputs/sim.ld %t.o -o %t
; RUN: %mipsx-run --print-exit %t | FileCheck %s
; CHECK: hello
; CHECK: exit: 0
```

lit runs RUN lines with `pipefail`, so a hazard (status 125) fails the
test even when piped into FileCheck; use `--print-exit` or
`--expect-exit` for programs that exit non-zero on purpose.

## What is modelled

**ELF.** ELF32, big-endian (`ELFDATA2MSB`), `EM_MIPS_X` (51), `ET_EXEC`.
`PT_LOAD` segments are loaded at their physical (load) address, as the
device's loader would; `.data` copying is crt0's job. `e_flags` may be
0 or `EF_MIPSX_ES3890`; without that flag the six byte and halfword
memory instructions are errors. `EF_MIPSX_VSHIFT` and reserved bits are
rejected. Execution starts at `e_entry`.

**Reset state.** All registers 0 except sp (r29) = top of RAM − 16, so
that small tests can run without crt0 (crt0 sets sp itself). PSW = S, I,
M, V and e set: system state, interrupts masked, overflow traps masked,
PC chain shifting on.

**Memory.** RAM from 0 to `--mem-size`, big-endian, plus the I/O page.
Anything else is an error. The simulator does not model the system/user
address split of manual §2.5.

**Instructions.** All of spec §3 to §6, decoded strictly: undefined
encodings (branch conditions 000 and 100, unknown function codes, a
shift field whose low four bits are not one-hot, compute-immediate OP
001 other than `hsc`, bad special register numbers) stop the simulation.
Arithmetic never traps on overflow (abi §13.3).

**Pipeline.** A three-entry fetch queue gives the two delay slots of
every branch and jump: a jump target takes effect three fetches later,
so overlapping transfers (like the `jpcrs; jpc; jpc` return sequence)
behave as on the hardware. A squashing branch that is not taken turns
its two slots into bubbles: they take a cycle each but have no effect,
and they do not count as uses of a loaded register.

**Cycles.** One cycle per instruction or squashed slot, one extra when a
memory instruction follows a store (manual §3.3, P6), two bubbles after
`trap`. Cache misses are not modelled.

**MD and steps.** `mstart`, `mstep` and `dstep` as in spec §5.

**PSW.** Bit positions from manual Figure 2-3, which the spec does not
confirm for the ES3890 (LSB-first: S 0, s 1, I 2, i 3, M 4, m 5, V 6,
v 7, e 8, E 9–12, o 28, O 29, u 30, U 31). `movtos psw` writes every
bit except e and E in system state and does nothing in user state.
`trap` copies PSWcurrent to PSWother and enters system state with
interrupts and overflow masked and PC shifting off; `jpcrs` copies
PSWother back (in system state) and turns shifting on. There are no
interrupt sources, so I and the E chain never change.

**PC chain and traps.** `trap #v` jumps to word v × 8. The two
instructions behind it are killed: the first is the one the handler
restarts, as in manual Figure VI-2. The chain is frozen holding the
previous instruction, the trap and the restart address; `movfrs pcm4`
reads and shifts it, `movtos pcm1` shifts a value in, and `jpc`/`jpcrs`
jump to the PC-4 end and rotate it while shifting is on. Reading the
chain while it is shifting (outside a handler) gives the last frozen
contents rather than live pipeline PCs.

`hsc` stops the simulation with an error.

## Hazards reported

Each check reports the PC and both instructions involved. In `error`
mode (the default) the first one stops the run with status 125; in
`warn` mode it is printed (up to 100) and execution continues with
sequential semantics, except that a misaligned access drops the low
address bits as the hardware does; `off` checks nothing.

| Rule (abi §9) | Check |
|---|---|
| P1 | The instruction after a load (in execution order, across taken branches and jumps) reads the load's destination as Src1, Src2, store data, branch operand or `jspci` base |
| P2 | A load whose destination is its address register |
| P3 | A branch, jump, `trap` or `hsc` in a delay slot, even a squashed one. Exception: the slots of `jpc` and `jpcrs`, which hold the restarted instructions of an exception return |
| §9.2 | A load in the second delay slot of a branch or jump, even a squashed one (same exception) |
| P4 | `mstart`, `mstep`, `dstep` or `movfrs md` right after `movtos md`; `movfrs md` or `movtos md` right after a step |
| P5 | Misaligned word or halfword access |
| P6 | Not a hazard: counted as a stall cycle |

## I/O page

At 0xFFFF0000, reachable from r0 with a negative offset. The first five
registers are abi §13.5; the rest are simulator extensions.

| Address | Offset from r0 | Access | Function |
|---|---|---|---|
| 0xFFFF0000 | −65536 | Store, any width | Write the low 8 bits to stdout |
| 0xFFFF0004 | −65532 | Store word | Exit; the status is the low 8 bits |
| 0xFFFF0008 | −65528 | Load word | Cycle counter, low word (latches the high word). Counts cycles before this instruction |
| 0xFFFF000C | −65524 | Load word | Cycle counter, high word, as latched |
| 0xFFFF0010 | −65520 | Load word | Next byte from stdin, or −1 at end of file |
| 0xFFFF0014 | −65516 | Store, any width | Write the low 8 bits to stderr (extension) |
| 0xFFFF0018 | −65512 | Load word | Instructions executed, low word (latches the high word; extension) |
| 0xFFFF001C | −65508 | Load word | Instructions executed, high word, as latched (extension) |

Other addresses in the page, and loads narrower than a word, are errors.

## Tests

`tests/mxasm.py` is a small assembler for the tests, written from the
spec independently of the simulator's decoder, with the abi.md syntax,
the §10.5 pseudo-instructions, local labels, `.rept`, and two test-only
pseudo-instructions: `expect rN,value` (exits with the source line
number if rN differs; clobbers r1) and `exit #n`. It writes a linked
ELF. `tests/run_tests.py` assembles and runs each `tests/*.s` and checks
the directives at its top (`; EXIT:`, `; STDOUT:`, `; STDERR:`,
`; ARGS:`, `; RUNNER:`, `; ELF:` and others; see the script). To run one
test: `python3 tests/run_tests.py --sim build/mipsx-sim --runner
./mipsx-run -v tests/alu.s`.

The assembler is only for these tests; real programs use the LLVM tools.

## Not done yet

- The lit configuration in the LLVM tree (S8): a `%mipsx-run`
  substitution and a linker script for simulator programs (S7).
- Interrupts and overflow traps (no interrupt sources; abi §13.3 says
  the simulator never traps on overflow).
- The system/user address split, and live PC chain contents outside
  exception handlers.
- The ES3890 variable shift (plan L2), once its encoding is known.
