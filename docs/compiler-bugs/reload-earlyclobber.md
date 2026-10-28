# Stack reloads are early-clobber `LD`s at a normal slot index

Found in S15 (picolibc). llvm-project `mipsx` at 67d0924e3e53 (plus S14's
uncommitted work in progress), assertions on.

**Status: fixed** in llvm-project 8530b3a411c7 (S14, "Reload spills
without the early-clobber of ld": reloads use `LDfi`, an `ld` without
the constraint). With it, `reload-earlyclobber.c` passes
`-verify-regalloc` and `strptime_l.c` compiles at `-O2`.

## Symptom

`libc/time/strptime_l.c` from picolibc crashes Clang at `-O2` and `-O3`
(segmentation fault in the greedy register allocator on `__strptime`);
`-O0`, `-O1`, `-Os` and `-Oz` compile. `llc -regalloc=basic` and
`-regalloc=fast` also compile it.

## Reproducer

[`reload-earlyclobber.c`](reload-earlyclobber.c) (twelve values live
across a call in a loop, so some are spilled) does not crash, but shows
the cause with the register allocation verifier:

```
clang --target=mipsx -O2 -S -emit-llvm reload-earlyclobber.c -o r.ll
llc -O2 -verify-regalloc r.ll -o /dev/null
```

```
*** Bad machine code: No live segment at def ***
- instruction: 1496B	early-clobber %113:gpr = LD %stack.0, 0 :: (load (s32) from %stack.0)
*** Bad machine code: Early clobber def must be at an early-clobber slot ***
```

The crash itself: build picolibc as `docs/picolibc.md` says with
`--buildtype=release`, or take the compile command for
`libc_time_strptime_l.c.o` from `build/picolibc/build.ninja`.

## Cause (as far as S15 looked)

The load format (`MIPSXInstrFormats.td`) carries `@earlyclobber $rd`, for
rule P2 (a load must not overwrite its address register).
`MIPSXInstrInfo::loadRegFromStackSlot` builds that same `LD` for reloads.
The spiller and live-range splitting index an inserted reload's def at
the register slot, not the early-clobber slot, so the live intervals no
longer match the instructions and greedy eventually follows a broken
segment. A reload's base is sp or fp, which is never the destination, so
a reload does not need the constraint (for example, a separate reload
opcode or pseudo without it, expanded or printed as `ld`).

## Other effects in picolibc (S15)

The same register allocation runs also hit two assertions with the
picolibc tests at `-Oz` (likely the same cause; not reduced):

- `test/test-iconv/test-iconv.c`: `LiveIntervals.cpp:574
  computeDeadValues: No instruction defining live value` (greedy, `main`).
- `test/testsuite/newlib.math/string.c`: `CalcSpillWeights.cpp:125
  isRematerializable: Dead valno in interval` (greedy, `test_string`).

`llc -O2 -verify-regalloc` on the IR of each picolibc library source
(built at `-Os`) reports this error in 75 of 1044 files, so some code
that compiles may be miscompiled. The worst (count of verifier errors):

```
22 libc/stdio/vfwscanf.c
22 libc/search/hash_page.c
15 libc/stdio/vflscanf.c
15 libc/stdio/vfiscanf.c
14 libc/search/qsort_r.c
13 libc/stdio/vfmscanf.c
12 libm/common/s_remquo.c
12 libc/search/hash.c
10 libm/math/k_rem_pio2.c
8 libc/stdlib/getopt.c
8 libc/stdio/vfscanf.c
8 libc/stdio/vffscanf.c
6 libc/stdio/wcstof.c
6 libc/stdio/ftoa_ryu.c
6 libc/posix/regexec.c
6 libc/posix/regcomp.c
5 libm/common/s_fma.c
4 libm/math/s_log.c
4 libm/math/s_j1.c
4 libc/stdlib/setenv.c
```

`test-fmemopen`'s `main` is another (2 errors at `-Oz`); it stops on the
simulator with a misaligned load through a pointer that should still
hold `&mode_rw2[i]`, which is what a wrong allocation would do.
