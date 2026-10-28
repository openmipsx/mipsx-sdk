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
; is set.  A multiplier that fits in k bits (signed) only needs its low k
; bits in the top of MD and k steps, so the routine picks the first of:
;
;   a fits in 8 bits      a << 24 in MD,  8 steps     14 cycles
;   a fits in 16 bits     a << 16 in MD, 16 steps     26 cycles
;   b fits in 16 bits     b << 16 in MD, 16 steps     30 cycles
;   otherwise             a in MD,       32 steps     48 cycles
;
; (signed ranges; cycles include the return).  Pipeline rule P4 (abi §9):
; one instruction between movtos md and the first step; the branch delay
; slots provide it.
;
; Clobbers r1-r3 and MD (a private guarantee: __muldi3 relies on it).

    .text
    .globl  __mulsi3
    .type   __mulsi3,@function
__mulsi3:
    lsl     r4,r1,#24
    asr     r1,r3,#24               ; r3 = a sign-extended from 8 bits
    bne     r3,r4,.Lnot8            ; a does not fit in 8 bits
    movtos  r1,md                   ; slot: MD = a << 24
    lsl     r4,r3,#16               ; slot: r3 = a << 16 (P4 gap)
    mstart  r5,r2                   ; 8 steps
    .rept 5
    mstep   r2,r5,r2
    .endr
    ret
    mstep   r2,r5,r2
    mstep   r2,r5,r2

.Lnot8:                             ; r3 = a << 16
    asr     r3,r1,#16               ; a sign-extended from 16 bits
    bne     r1,r4,.Lnot16a
    movtos  r3,md                   ; slot: MD = a << 16
    lsl     r5,r3,#16               ; slot: r3 = b << 16 (P4 gap)
    mstart  r5,r2                   ; 16 steps
    .rept 13
    mstep   r2,r5,r2
    .endr
    ret
    mstep   r2,r5,r2
    mstep   r2,r5,r2

.Lnot16a:                           ; r3 = b << 16
    asr     r3,r1,#16               ; b sign-extended from 16 bits
    bne     r1,r5,.Lfull
    movtos  r3,md                   ; slot: MD = b << 16
    nop                             ; slot (P4 gap)
    mstart  r4,r2                   ; 16 steps, a is the multiplicand
    .rept 13
    mstep   r2,r4,r2
    .endr
    ret
    mstep   r2,r4,r2
    mstep   r2,r4,r2

.Lfull:
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
