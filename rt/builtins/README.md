# rt/builtins: multiply, divide and shift helpers

Work package S12 (SDK half) of the LLVM backend plan. MIPS-X has no
multiply, divide or variable shift instructions (abi §1), so the code
generator calls these routines. They are hand-written assembly on
`mstart`, `mstep` and `dstep` (manual Appendix IV, spec §5), with the
names and C signatures of libgcc and compiler-rt, so that they can move
into compiler-rt's `lib/builtins/mipsx/` later (plan question L4).

| File | Symbols |
|---|---|
| `mulsi3.S` | `__mulsi3` |
| `muldi3.S` | `__muldi3` (calls `__mulsi3`) |
| `divsi3.S` | `__udivsi3`, `__umodsi3`, `__divsi3`, `__modsi3` |
| `divdi3.S` | `__udivdi3`, `__umoddi3`, `__divdi3`, `__moddi3` |
| `ashl.S` | `__ashlsi3`, `__ashldi3` |
| `lshr.S` | `__lshrsi3`, `__lshrdi3` |
| `ashr.S` | `__ashrsi3`, `__ashrdi3` |

## Calling convention

The standard one (abi §7): 32-bit arguments in r4, r5; 64-bit arguments
as register pairs, high word first (r4:r5, r6:r7); the shift amount of
the 64-bit shifts in r6; results in r2 or r2:r3. All are leaf-like (no
stack use), never touch r16–r30, and return with `jspci r31,#0,r0`.

The table lists what each routine actually changes. This is a promise
the backend may use (abi §7.4), for example by giving the libcall a
smaller clobber list than a normal call; the tests check it on every
call. r31 is changed by the call itself.

| Routine | Changes | Extra results |
|---|---|---|
| `__mulsi3` | r1–r3, MD | |
| `__muldi3` | r1–r5, r8–r15, MD | |
| `__udivsi3` | r1–r3, MD | r3 = remainder |
| `__umodsi3` | r1–r3, r15, MD | |
| `__divsi3`, `__modsi3` | r1–r5, r12, r13, r15, MD | |
| `__udivdi3` | r1–r11, MD | r4:r5 = remainder |
| `__umoddi3` | r1–r11, r15, MD | |
| `__divdi3`, `__moddi3` | r1–r13, r15, MD | |
| `__ashlsi3` | r1–r3, r5 | |
| `__lshrsi3`, `__ashrsi3` | r1–r3 | |
| `__ashldi3`, `__lshrdi3`, `__ashrdi3` | r1–r5 | |

So `udivrem` on i32 is one call to `__udivsi3` (quotient r2, remainder
r3), and on i64 one call to `__udivdi3` (quotient r2:r3, remainder r4:r5).

## Defined behaviour where C has none

- **Division by zero** does not trap: `n / 0 = 0` and `n % 0 = n`, signed
  and unsigned, 32 and 64 bits (as Arm's `SDIV`/`UDIV`). The identity
  `n == (n / d) * d + n % d` still holds.
- `INT_MIN / -1 = INT_MIN`, `INT_MIN % -1 = 0` (and the same for 64 bits).
- Shift amounts use only their low 5 bits (6 for the 64-bit shifts).

## Cycles

Measured on `mipsx-sim` from the first instruction to the end of the
return's delay slots (add 3 for the call). `python3
rt/tests/test_builtins.py --cycles` prints min/max/mean over the test
rows.

| Routine | Cycles |
|---|---|
| `__mulsi3` | 35, whatever the operands (constant-time) |
| `__muldi3` | 62 (high words 0, bl < 2^16), 94 (high words 0), about 100 (one high word −1), up to 172 |
| `__udivsi3` | 25 (n < 2^8), 33 (n < 2^16), 43, 10 (d = 0), 13–15 (d > 2^31) |
| `__umodsi3` | `__udivsi3` + 7 |
| `__divsi3`, `__modsi3` | `__udivsi3` + 13 |
| `__udivdi3` | 46 (d ≤ 2^31, nh < d), about 82 (d ≤ 2^31), 13 (n < d or d = 0), else about 110 + 18 per quotient bit, at most about 700 |
| `__umoddi3` | `__udivdi3` + 7 |
| `__divdi3`, `__moddi3` | `__udivdi3` + 16 to 24 |
| 32-bit shifts | 10 |
| 64-bit shifts | 14 |

Means over the test rows (biased towards edge cases): `__mulsi3` 35,
`__udivsi3` 27, `__divsi3` 47, `__muldi3` 127, `__udivdi3` 74.

## How they work

- **Multiply**: MD holds the multiplier, consumed from its top bit; a
  multiplier that fits in k bits is put at the top of MD and needs only
  k steps. `__mulsi3` always takes all 32, so that its time does not
  depend on the operands (BearSSL's EC and GHASH code multiply secrets);
  the compiler does the narrow cases inline when known bits show an
  operand fits in 17 bits or fewer. It used to choose 8 or 16 steps
  at run time (14 to 48 cycles); over BearSSL's `m15` EC code the
  constant-time version costs 23–27%. `__muldi3` is not constant-time:
  it skips terms when a high word or the top half of bl is 0. `__muldi3`
  builds the 64-bit product of the low words from
  four 16 × 16 products (two `movtos` of the same word: after 16 steps MD
  holds the low half at the top) and adds the cross terms from
  `__mulsi3`.
- **Divide**: `dstep` is exact for divisors up to 2^31; larger divisors
  (quotient 0 or 1) and zero take a short path. 64-bit division with a
  divisor up to 2^31 is two chained 32-step divisions (the remainder of
  the first seeds the second); other divisors use an aligned
  shift-and-subtract loop over at most 33 quotient bits.
- **Shifts**: a jump into a 32-entry table of immediate `sh`/`asr`
  instructions, each entry `ret` plus two delay-slot instructions. The
  table address comes from a `jspci` to the next instruction (the return
  address register gives the PC), so no `la` is needed. The 64-bit
  shifts move a word across first when the amount is 32 or more, then
  share the table (the `sh` funnel shift does the cross-word part).
  Tables: 128 words per file.

Every routine follows abi §9 (the simulator reports no hazards):
explicit delay slots, one instruction between `movtos md` and a step,
and between the last step and `movfrs md`.

## Tests

`rt/tests/test_builtins.py` (run by the top-level `make check`)
generates, per routine, a program with a table of inputs and expected
outputs computed in Python with C semantics, links it with crt0 using
`sim/tests/mxasm.py` and runs it on the simulator. Rows: the cross
product of a set of edge values (0, ±1, ±2, ±3, the extremes, powers of
two and their neighbours, their negations, some patterns), each value of
a larger edge set against a few partners, and 3000 random pairs with
random bit lengths; for shifts, every edge value with every amount 0–31
(0–63) plus out-of-range amounts and 1000 random pairs. 15,352 rows for
each 32-bit two-operand routine, 14,236 for each 64-bit one, 7,296 and
26,368 for each 32- and 64-bit shift: about 196,000 in all. After each
call the program checks the result and every register outside the clobber
list above (canaries in the scratch registers, inputs in unchanged
argument registers, sp, r16, r23, r24, r28). A failure prints the
routine, the arguments, the expected and actual values.

## For the backend (S12 proper)

- Libcall names: the LLVM defaults (`RuntimeLibcalls.td`): `__mulsi3`,
  `__muldi3`, `__[u]divsi3`, `__[u]modsi3`, `__[u]divdi3`,
  `__[u]moddi3`, `__ashlsi3`, `__lshrsi3`, `__ashrsi3`, `__ashldi3`,
  `__lshrdi3`, `__ashrdi3`. The 64-bit shift amount is an `i32` in r6.
- `MD` is clobbered by every multiply and divide helper; it is
  caller-saved anyway.
- Multiplication by a constant should be expanded inline (shifts and
  adds) rather than calling `__mulsi3`; division by a constant should
  stay a call (there is no cheap high multiply). The backend also
  multiplies inline with `mstep` when an operand is known to be narrow
  (`MULSTEPS`), and pads a nop between a call's return and a `movtos md`,
  since `__mulsi3` ends with two `mstep`s in its return delay slots.
- Linking: until there is an archive, link the `.S` files needed. Each
  file is one object; `muldi3.S` needs `mulsi3.S`.
