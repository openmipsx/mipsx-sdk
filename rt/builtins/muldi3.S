; muldi3.S: __muldi3, 64-bit multiplication.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Run-time helper for the code generator (work package S12; see
; rt/builtins/README.md).  As in libgcc and compiler-rt:
;
;   long long __muldi3(long long a, long long b)
;       r2:r3 = low 64 bits of (r4:r5) * (r6:r7)    (high word first)
;
; Signed and unsigned operands give the same low 64 bits.  With a = ah:al
; and b = bh:bl,
;
;   a * b = al * bl  +  ((ah * bl + al * bh) << 32)     (mod 2^64)
;
; The cross terms only need their low 32 bits: __mulsi3, called only when
; ah or bh is non-zero (its short cases make ah or bh = -1 cheap).  The
; full 64-bit product al * bl is built from 16-bit halves (al = a1:a0,
; bl = b1:b0), each product 16 msteps with the 16-bit multiplicand added
; to a partial product that cannot overflow:
;
;   MD = al:  16 steps with b0 give a1*b0; MD is then a0 << 16, so 16
;             more steps with b0 give a0*b0.  Again with b1 (skipped when
;             b1 = 0) for a1*b1 and a0*b1.
;   mid = a0*b1 + a1*b0  (33 bits)
;   lo  = a0*b0 + (mid << 16),  hi = a1*b1 + (mid >> 16) + carries.
;
; Cycles, including the return: 62 when ah = bh = 0 and bl < 2^16, 94
; when ah = bh = 0, up to about 200 with both cross terms (README).
;
; Clobbers r1-r5, r8-r15 and MD (relies on __mulsi3 clobbering only r1-r3
; and MD).

    .text
    .globl  __muldi3
    .type   __muldi3,@function
__muldi3:
    mov     r31,r15                 ; return address (__mulsi3 calls)
    beq     r4,r0,.Lno_ah           ; ah = 0: no ah * bl term
    mov     r5,r8                   ; slot: r8 = al
    mov     r0,r12                  ; slot: cross = 0
    call    __mulsi3                ; r2 = ah * bl
    mov     r7,r5                   ; slot: second argument bl (r4 = ah)
    nop
    mov     r2,r12
.Lno_ah:
    beq     r6,r0,.Lno_bh           ; bh = 0: no al * bh term
    mov     r6,r4                   ; slot: first argument bh (the
    mov     r8,r5                   ; slot:  multiplier), second al
    call    __mulsi3                ; r2 = bh * al
    nop
    nop
    add     r12,r2,r12              ; cross = ah * bl + al * bh
.Lno_bh:
    movtos  r8,md                   ; MD = al: a1 first, then a0
    lsl     r7,r9,#16               ; P4 gap
    lsr     r9,r9,#16               ; r9 = b0
    mstep   r0,r9,r10               ; r10 = a1 * b0
    .rept 15
    mstep   r10,r9,r10
    .endr
    mstep   r0,r9,r11               ; r11 = a0 * b0
    .rept 15
    mstep   r11,r9,r11
    .endr
    lsr     r7,r13,#16              ; r13 = b1 (P4 gap after the step)
    mov     r0,r1                   ; a0 * b1 = 0 if b1 = 0
    beq     r13,r0,.Lsum
    movtos  r8,md                   ; slot: MD = al again
    mov     r0,r14                  ; slot: a1 * b1 = 0 if b1 = 0 (P4 gap)
    mstep   r0,r13,r14              ; r14 = a1 * b1
    .rept 15
    mstep   r14,r13,r14
    .endr
    mstep   r0,r13,r1               ; r1 = a0 * b1
    .rept 15
    mstep   r1,r13,r1
    .endr
.Lsum:                              ; r1 = a0*b1, r10 = a1*b0, r11 = a0*b0, r14 = a1*b1
    add     r1,r10,r9               ; mid = a0*b1 + a1*b0
    mov     r0,r13
    blosq   r9,r10,1f               ; carry out of mid: run the slots
    addi    r0,#1,r13               ; r13 = carry
    nop
1:  sh      r9,r13,r13,#16          ; (carry:mid) >> 16
    add     r14,r13,r2              ; hi = a1*b1 + (carry:mid) >> 16
    lsl     r9,r9,#16
    add     r11,r9,r3               ; lo = a0*b0 + (mid << 16)
    blosq   r3,r9,2f                ; carry out of lo: run the slots
    addi    r2,#1,r2
    nop
2:  jspci   r15,#0,r0               ; return
    add     r2,r12,r2               ; slot: hi += cross terms
    nop
    .size   __muldi3,.-__muldi3
