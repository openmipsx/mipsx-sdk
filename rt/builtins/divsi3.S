; divsi3.S: __udivsi3, __umodsi3, __divsi3 and __modsi3, 32-bit division.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Run-time helpers for the code generator (work package S12; see
; rt/builtins/README.md).  As in libgcc and compiler-rt, with n in r4,
; d in r5 and the result in r2:
;
;   unsigned __udivsi3(unsigned n, unsigned d)    n / d
;   unsigned __umodsi3(unsigned n, unsigned d)    n % d
;   int      __divsi3(int n, int d)               n / d, truncated
;   int      __modsi3(int n, int d)               n % d, sign of n
;
; __udivsi3 also leaves the remainder n % d in r3, so one call gives both
; (a private convention the backend may use for udivrem).
;
; Division by zero does not trap: n / 0 = 0 and n % 0 = n, signed or
; unsigned (as on Arm; the identity n = (n / d) * d + n % d still holds).
; INT_MIN / -1 = INT_MIN and INT_MIN % -1 = 0 (undefined in C).
;
; Method: manual Appendix IV.  dstep is one step of restoring division:
; with the remainder in a register and the dividend in MD it shifts the
; next dividend bit into the remainder, subtracts d if it fits and shifts
; the quotient bit into MD.  It is exact while the remainder stays below d
; and d <= 2^31; larger divisors (and zero) take a separate path where
; the quotient is 0 or 1.  A dividend below 2^8 (2^16) needs only 8 (16)
; steps with its bits at the top of MD.  Cycles, including the return:
;
;   __udivsi3   25 (n < 2^8), 33 (n < 2^16), 43 (other n), 10 (d = 0),
;               13-15 (d > 2^31)
;   __umodsi3   __udivsi3 + 7
;   __divsi3, __modsi3   __udivsi3 + 13
;
; Clobbers (private guarantees, used by the signed versions):
;   __udivsi3: r1-r3, MD
;   __umodsi3: r1-r3, r15, MD
;   __divsi3, __modsi3: r1-r5, r12, r13, r15, MD

    .text
    .globl  __udivsi3
    .type   __udivsi3,@function
__udivsi3:                          ; r2 = r4 / r5, r3 = r4 % r5
    addi    r5,#-1,r1
    bltsq   r1,r0,.Lspecial         ; d = 0 or d > 2^31: run the slots
    mov     r4,r3                   ; r = n
    mov     r0,r2                   ; q = 0
    lsr     r4,r1,#16
    bne     r1,r0,.Ld32             ; n >= 2^16: 32 steps
    movtos  r4,md                   ; slot: MD = n
    mov     r0,r3                   ; slot: r = 0 (and the P4 gap)
    lsr     r4,r1,#8
    bne     r1,r0,.Ln16             ; n >= 2^8: 16 steps
    lsl     r4,r2,#16               ; slot: r2 = n << 16
    lsl     r4,r1,#24               ; slot: r1 = n << 24
    movtos  r1,md                   ; n < 2^8: 8 steps
    b       .Ld8
    dstep   r3,r5,r3                ; slot: step 25
    dstep   r3,r5,r3                ; slot: step 26
.Ln16:
    movtos  r2,md
    b       .Ld16
    dstep   r3,r5,r3                ; slot: step 17
    dstep   r3,r5,r3                ; slot: step 18
.Ld32:
    .rept 18
    dstep   r3,r5,r3                ; steps 1-18
    .endr
.Ld16:
    .rept 8
    dstep   r3,r5,r3                ; steps 19-26
    .endr
.Ld8:
    .rept 6
    dstep   r3,r5,r3                ; steps 27-32
    .endr
    ret
    nop                             ; P4: no movfrs md right after a step
    movfrs  md,r2                   ; slot: q

.Lspecial:                          ; q = 0, r = n
    beq     r5,r0,.Lret             ; d = 0
    nop
    nop
    blo     r4,r5,.Lret             ; n < d
    nop
    nop
    sub     r4,r5,r3                ; d > 2^31 and n >= d: q = 1
    addi    r0,#1,r2
.Lret:
    ret
    nop
    nop
    .size   __udivsi3,.-__udivsi3

    .globl  __umodsi3
    .type   __umodsi3,@function
__umodsi3:                          ; r2 = r4 % r5
    mov     r31,r15
    call    __udivsi3
    nop
    nop
    jspci   r15,#0,r0               ; return
    mov     r3,r2                   ; slot: the remainder
    nop
    .size   __umodsi3,.-__umodsi3

    .globl  __divsi3
    .type   __divsi3,@function
__divsi3:                           ; r2 = r4 / r5
    asr     r4,r12,#31              ; sign of n (0 or -1)
    asr     r5,r13,#31              ; sign of d
    xor     r4,r12,r4
    sub     r4,r12,r4               ; |n|
    xor     r5,r13,r5
    mov     r31,r15
    call    __udivsi3
    sub     r5,r13,r5               ; slot: |d|
    xor     r12,r13,r13             ; slot: sign of the quotient
    xor     r2,r13,r2
    jspci   r15,#0,r0               ; return
    sub     r2,r13,r2               ; slot: negate if the signs differ
    nop
    .size   __divsi3,.-__divsi3

    .globl  __modsi3
    .type   __modsi3,@function
__modsi3:                           ; r2 = r4 % r5
    asr     r4,r12,#31              ; sign of n
    asr     r5,r13,#31              ; sign of d
    xor     r4,r12,r4
    sub     r4,r12,r4               ; |n|
    xor     r5,r13,r5
    mov     r31,r15
    call    __udivsi3
    sub     r5,r13,r5               ; slot: |d|
    nop
    xor     r3,r12,r2
    jspci   r15,#0,r0               ; return
    sub     r2,r12,r2               ; slot: the remainder has the sign of n
    nop
    .size   __modsi3,.-__modsi3
