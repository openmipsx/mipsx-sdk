# mipsx-sim: MIPS-X (ES3890) instruction-set simulator

Runs a linked MIPS-X ELF executable and reports every violation of the
pipeline rules in [`../docs/abi.md`](../docs/abi.md) §9 that it sees,
instead of silently computing a wrong answer. Written from the
[processor spec](https://github.com/openmipsx/devices/blob/main/common/processor-es3890.md), the ABI and the
public MIPS-X manual. Work package S6 of the LLVM backend plan.

## Building and testing

```
make            # builds build/mipsx-sim (any C11 compiler)
make check      # runs the tests (needs python3)
make install PREFIX=...   # installs mipsx-sim and mipsx-run into PREFIX/bin
```

## Running

```
mipsx-sim [options] program.elf [argument...]
```

Options stop at `program.elf`; it and the words after it are the
program's command line, `argv[0]` being the path as given. crt0 passes
them to `main` through the I/O page (abi §13.3, §13.5).

| Option | Meaning |
|---|---|
| `-t`, `--trace` | Trace every instruction to stderr: cycle, byte address, word, disassembly, effect (register written, memory address, branch outcome, squashed slots) |
| `--trace-file=FILE` | Trace to FILE |
| `-c N`, `--max-cycles=N` | Stop after N cycles with status 124 (default 10⁹; 0 = no limit) |
| `--hazards=error\|warn\|off` | What a pipeline rule violation does (default `error`) |
| `-w`, `--warn-hazards` | Same as `--hazards=warn` |
| `--hazard-rules=all\|hardware` | Which rules to check (default `all`). `hardware` leaves out the ABI conventions (see "Hazards reported"), for code the vendor's compiler or other tools wrote |
| `-m N`, `--mem-size=N` | Size of RAM at address 0 (default 0x200000, the device's 2 MB) |
| `-s`, `--stats` | At exit, print cycles, instructions, squashed slots, store stalls and delay-slot use (how many slots hold `nop`; for S11) |
| `-d`, `--disassemble` | Print the disassembly of the executable segments and exit |
| `--variant=NAME,...` | Simulate an alternative reading of the spec (see "Variants"); repeatable. `--variant=list` lists them |

Exit status: the program's exit status (the low 8 bits of the word
stored to the exit register), or

| Status | Meaning |
|---|---|
| 124 | Cycle limit reached |
| 125 | Simulation error: pipeline hazard (in `error` mode), undefined or unknown instruction, access to unmapped memory, fetch outside RAM, `hsc` |
| 126 | The program could not be loaded, or bad options |

Diagnostics go to stderr, prefixed `mipsx-sim: error:` or `warning:`,
with the PC as a byte address and the nearest symbol. Hazard reports end
with the class of the rule broken, for example:

```
mipsx-sim: error: pc 0x00002008 <_start+0x8>: load-use hazard (P1): mov r4,r5 reads r4, loaded by the previous instruction at 0x00002004 <_start+0x4> [hardware rule] (cycle 3)
```

## The runner, `mipsx-run`

For lit and other harnesses. It finds the simulator (`$MIPSX_SIM`, else
`mipsx-sim` next to the script, else `build/mipsx-sim` next to it, else
`PATH`), passes all other options and arguments to it in order, and adds:

| Option | Meaning |
|---|---|
| `--expect-exit=N` | Exit 0 if the program's status is N, else print a message and exit 1 |
| `--print-exit` | After the run, print `exit: N` on stdout, for FileCheck |
| `--args STRING` | Split STRING at blanks (no globbing) and append the words to the program's arguments. picolibc's tests pass their command line this way, after the ELF; may be repeated |

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
shift field whose low four bits are not one-hot, bad special register
numbers) stop the simulation. So do compute-immediate OP 001 encodings
other than `hsc`, reported as an "unknown instruction": spec §6 says
later firmware executes them, but not what they do. Arithmetic never
traps on overflow (abi §13.3).

Where the spec marks a fact **Simulated** (vendor code run on this
simulator, checked against an independent oracle), the simulator
follows it: opcode 100 (`ldbu`) zero-extends, `bic` is ~Src1 & Src2,
and SQ = 1 squashes the slots of a branch that is not taken. The
signedness of opcodes 101, 001 and 111 is still a Hypothesis (spec §3).

**Code addresses.** Word addresses are 30 bits wide (spec §1): branch,
`jspci`, `jpc` and `jpcrs` targets and the sequential PC are taken modulo
2³⁰ words, so a `jspci` whose Src1 + offset has bit 30 or 31 set lands
on bits 29–0 (spec §6, "Target wrap"). A wrapped target outside RAM is
still a fetch error.

**Pipeline.** A three-entry fetch queue gives the two delay slots of
every branch and jump: a jump target takes effect three fetches later,
so overlapping transfers (like the `jpcrs; jpc; jpc` return sequence)
behave as on the hardware. A squashing branch that is not taken turns
its two slots into bubbles: they take a cycle each but have no effect,
and they do not count as uses of a loaded register.

**Cycles.** One cycle per instruction or squashed slot, one extra when a
memory instruction follows a store (manual §3.3, P6; spec §9 confirms
the pair is legal but not whether it stalls), two bubbles after
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
address bits as the hardware does; `off` checks nothing. At exit, `warn`
mode prints the number of reports for each rule, including those past
the first 100.

Each report is tagged with the class of its rule. A **hardware rule**
comes from the manual and nothing in the spec contradicts it. An **ABI
convention** is a rule of abi §9 that the hardware does not need: spec
§9 found the vendor's code breaking it on the device, or the manual
allows what the ABI forbids. Our compiler still follows the conventions,
so the default (`--hazard-rules=all`) checks them;
`--hazard-rules=hardware` leaves them out. A **variant rule** comes from
`--variant` and is checked whenever its variant is on.

| Rule (abi §9) | Class | Check |
|---|---|---|
| P1 | Hardware | The instruction after a load (in execution order, across taken branches and jumps) reads the load's destination as Src1, Src2, store data, branch operand or `jspci` base. Spec §9: one load delay slot |
| P2 | Convention | A load whose destination is its address register. Spec §9: works on the hardware and gives the loaded value |
| P3 | Hardware | A branch, jump, `trap` or `hsc` in a delay slot that executes. Exception: the slots of `jpc` and `jpcrs`, which hold the restarted instructions of an exception return |
| P3, squashed slot | Convention | The same in a slot that is squashed, which the manual allows |
| §9.2 | Convention | A load in the second delay slot of a branch or jump, even a squashed one (same exception). Spec §9: legal on the hardware |
| P4 | Hardware | `mstart`, `mstep`, `dstep` or `movfrs md` right after `movtos md` |
| P4, after a step | Convention | `movfrs md` or `movtos md` right after a step; stricter than the manual |
| P5 | Hardware | Misaligned word or halfword access |
| P6 | — | Not a hazard: counted as a stall cycle. Spec §9: legal |

## Variants

The simulator follows the spec, and the compiler was tested against the
simulator, so a wrong fact in the spec would leave every test passing.
A variant replaces one fact that rests on a Hypothesis, or on the manual
alone, with a plausible alternative. If a program that passes normally
fails under a variant, the program depends on that fact, and the fact
needs checking on hardware. Some variants were written before the spec
settled their fact by simulation (marked "settled" below); they stay so
that a program's dependence on the fact can still be shown, but a
failure under them no longer points at an open question. `tests/variant_sweep.py` runs whole suites
this way (`../tests/README.md`).

Semantic variants change what an instruction does:

| Variant | Instead of the spec |
|---|---|
| `ldb-swap` | Opcode 100 (`ldbu`) sign-extends and 101 (`ldb`) zero-extends. Half settled: spec §3 says 100 zero-extends (Simulated); 101 is still a Hypothesis |
| `ldh-swap` | The same for halfwords: 001 (`ldhu`) sign-extends, 111 (`ldh`) zero-extends |
| `bic-swap` | `bic` is Src1 & ~Src2, as the manual's comment column says, not Src2 & ~Src1. Settled: spec §5 confirms ~Src1 & Src2 (Simulated) |
| `shift32-zero` | `sh` and `asr` with n = 32 (shift field e = 0) shift by 0, as a 5-bit shifter would |
| `squash-taken` | SQ = 1 squashes the delay slots when the branch is taken rather than when it is not. Settled: spec §4 confirms the spec reading (Simulated) |
| `dstep-borrow` | `dstep` subtracts when the 33-bit value (Src1 << 1 \| MSB(MD)) is at least Src2, rather than when the 32-bit difference has its MSB clear. The two agree whenever Src2 ≤ 2³¹ and the partial remainder is below Src2 |

Rule variants add a pipeline rule, reported as a hazard like those
above (`--hazards` applies):

| Variant | Extra rule |
|---|---|
| `load-delay-2` | Loads have two delay slots: P1 also applies to the second instruction after a load (a squashed slot counts as one). Settled: spec §9 says one slot (Simulated) |
| `store-mem` | A memory instruction right after a store is a hazard rather than a stall (P6). Settled: spec §9 says the pair is legal (Simulated) |
| `md-delay-2` | P4 also applies with one instruction in between |
| `icache` | Fetching a word that was stored to since the program was loaded is a hazard: an instruction cache that stores do not update |

There is no PSW variant: nothing in the simulator raises an interrupt,
so a wrong PSW layout cannot change what a program computes here.

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
| 0xFFFF0020 | −65504 | Load word | `argc` (extension) |
| 0xFFFF0024 | −65500 | Load word | Bytes the argv block needs, a multiple of 8 (extension) |
| 0xFFFF0028 | −65496 | Store word | Write the argv block at the stored address: `argc` + 1 word pointers (the last null), then the strings (extension) |

Other addresses in the page, loads narrower than a word, and an argv
block address that is not word aligned or whose block does not fit in
RAM are errors.

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

It also takes several source files (or `--link`) and links them into
one program the way `rt/sim.ld` would: `.text`, `.data`, `.bss`,
`.rodata` and `.section` directives, `.set`, `.p2align`/`.balign`,
file-local `.L` labels, and the linker-defined symbols of abi §13.1
(`link_layout()`), with test options to run `.data` away from its load
address (`--data-vma`) and to preload `.bss` with junk (`--bss-fill`).
The tests in `rt/` and `tools/` use this to build programs with crt0
until LLVM's assembler and lld support MIPS-X.

The assembler is only for these tests; real programs use the LLVM tools.

## Not done yet

- The lit configuration in the LLVM tree (S8): a `%mipsx-run`
  substitution and a linker script for simulator programs (S7).
- Interrupts and overflow traps (no interrupt sources; abi §13.3 says
  the simulator never traps on overflow).
- The system/user address split, and live PC chain contents outside
  exception handlers.
- The ES3890 variable shift (plan L2), once its encoding is known.
