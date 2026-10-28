; mulsi3.S: __mulsi3, 32-bit multiplication.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Run-time helper for the code generator (work package S12; see
; rt/builtins/README.md).  As in libgcc and compiler-rt:
;
;   int __mulsi3(int a, int b)      r2 = low 32 bits of r4 * r5
;
; The low 32 bits are the same for signed and unsigned operands, so this
; serves both.
;
; Method: manual Appendix IV.  MD holds the multiplier and is consumed
; from its most significant bit.  mstart handles the sign bit (-b if set),
; then each mstep doubles the partial product and adds b if the next bit
; is set.
;
; Always all 32 steps: 35 cycles including the return, whatever the
; operands, so that code multiplying secrets (BearSSL's EC and GHASH) does
; not leak them through timing.  Narrow multiplications are the
; compiler's job: when known bits show an operand fits in 17 bits or
; fewer it multiplies inline with that many steps (MIPSX backend,
; MULSTEPS).  A short path chosen here would depend on the values.
;
; Pipeline rule P4 (abi §9): one instruction between movtos md and the
; first step.  The last two steps are in the return's delay slots, so
; the caller must not start with movtos or movfrs md (the compiler puts
; a nop there).
;
; Clobbers r1-r3 and MD (a private guarantee: __muldi3 relies on it;
; only r2 and MD change).

    .text
    .globl  __mulsi3
    .type   __mulsi3,@function
__mulsi3:
    movtos  r4,md                   ; MD = a
    nop                             ; P4 gap
    mstart  r5,r2                   ; 32 steps
    .rept 29
    mstep   r2,r5,r2
    .endr
    ret
    mstep   r2,r5,r2
    mstep   r2,r5,r2
    .size   __mulsi3,.-__mulsi3
