; divdi3.S: __udivdi3, __umoddi3, __divdi3 and __moddi3, 64-bit division.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Run-time helpers for the code generator (work package S12; see
; rt/builtins/README.md).  As in libgcc and compiler-rt, with n in r4:r5,
; d in r6:r7 and the result in r2:r3 (high word first, abi §7):
;
;   unsigned long long __udivdi3(unsigned long long n, unsigned long long d)
;   unsigned long long __umoddi3(unsigned long long n, unsigned long long d)
;   long long          __divdi3(long long n, long long d)     truncated
;   long long          __moddi3(long long n, long long d)     sign of n
;
; __udivdi3 also leaves the remainder in r4:r5 (a private convention).
; Division by zero does not trap: n / 0 = 0 and n % 0 = n.  INT64_MIN / -1
; = INT64_MIN and INT64_MIN % -1 = 0.
;
; Method:
;
; A. d < 2^32 and d <= 2^31 (the usual case): long division by words
;    with dstep (see divsi3.S).  If nh >= d, 32 steps divide nh by d;
;    then 32 more steps divide (remainder:nl) by d, which is exact because
;    the remainder starts below d.  If nh < d the first division is
;    skipped (quotient high word 0, remainder nh).
;
; B. Otherwise (d >= 2^32, 2^31 < d < 2^32, or d = 0): if n < d the
;    quotient is 0.  Else the quotient has at most 33 bits; shift d left
;    by s = clz(d) - clz(n) so its top bit lines up with n's, then do
;    s + 1 steps of shift-and-subtract division on 64-bit values.
;
; Cycles, including the return (see the README for measured figures):
; A: 46 when nh < d, about 82 otherwise.  B: 13 when n < d or d = 0,
; else about 110 + 18 per quotient bit (at most 33 bits, about 700).
;
; Clobbers (private guarantees, used by the wrappers below):
;   __udivdi3: r1-r11, MD
;   __umoddi3: r1-r11, r15, MD
;   __divdi3, __moddi3: r1-r13, r15, MD

    .text
    .globl  __udivdi3
    .type   __udivdi3,@function
__udivdi3:                          ; q = r2:r3, r = r4:r5
    bne     r6,r0,.Lbig             ; d >= 2^32
    addi    r7,#-1,r1               ; slot
    nop                             ; slot
    blt     r1,r0,.Lbig             ; d = 0 or d > 2^31
    nop
    nop
    ; A: 1 <= d <= 2^31, d = r7.  Remainder in r8.
    blo     r4,r7,.La_low           ; nh < d: q high = 0, remainder nh
    mov     r4,r8                   ; slot
    mov     r0,r2                   ; slot
    movtos  r4,md                   ; MD = nh
    mov     r0,r8                   ; remainder 0 (P4 gap)
    .rept 32
    dstep   r8,r7,r8
    .endr
    nop                             ; P4: no movfrs md right after a step
    movfrs  md,r2                   ; q high = nh / d
.La_low:
    movtos  r5,md                   ; MD = nl
    mov     r0,r4                   ; r high = 0 (P4 gap)
    .rept 32
    dstep   r8,r7,r8
    .endr
    ret
    mov     r8,r5                   ; slot: r low
    movfrs  md,r3                   ; slot: q low

.Lbig:                              ; B
    or      r6,r7,r1
    beq     r1,r0,.Lret             ; d = 0: q = 0, r = n
    mov     r0,r2                   ; slot: q = 0
    mov     r0,r3                   ; slot
    blo     r4,r6,.Lret             ; nh < dh: n < d
    nop
    nop
    bne     r4,r6,.Lgo              ; nh > dh: n > d
    nop
    nop
    blo     r5,r7,.Lret             ; nh = dh and nl < dl
    nop
    nop
.Lgo:                               ; n >= d, d >= 2^31
    mov     r6,r10
    jspci   r0,#%call(.Lclz64),r8   ; r1 = clz(d)
    mov     r7,r11                  ; slot
    nop                             ; slot
    mov     r1,r9
    mov     r4,r10
    jspci   r0,#%call(.Lclz64),r8   ; r1 = clz(n)
    mov     r5,r11                  ; slot
    nop                             ; slot
    sub     r9,r1,r9                ; s = clz(d) - clz(n), 0..32
    ; d <<= s, one bit of s at a time
    lsl     r9,r1,#26               ; bit 5 (32)
    bltsq   r1,r0,1f
    mov     r7,r6
    mov     r0,r7
1:  lsl     r9,r1,#27               ; bit 4 (16)
    bltsq   r1,r0,1f
    sh      r7,r6,r6,#16
    lsl     r7,r7,#16
1:  lsl     r9,r1,#28               ; bit 3 (8)
    bltsq   r1,r0,1f
    sh      r7,r6,r6,#24
    lsl     r7,r7,#8
1:  lsl     r9,r1,#29               ; bit 2 (4)
    bltsq   r1,r0,1f
    sh      r7,r6,r6,#28
    lsl     r7,r7,#4
1:  lsl     r9,r1,#30               ; bit 1 (2)
    bltsq   r1,r0,1f
    sh      r7,r6,r6,#30
    lsl     r7,r7,#2
1:  lsl     r9,r1,#31               ; bit 0 (1)
    bltsq   r1,r0,.Lloop
    sh      r7,r6,r6,#31
    lsl     r7,r7,#1
.Lloop:                             ; s + 1 times: q = 2q + (n >= d), n -= d if so, d >>= 1
    sh      r3,r2,r2,#31            ; q high = q << 1
    blo     r4,r6,.Lnext            ; nh < dh: n < d
    add     r3,r3,r3                ; slot: q low = q << 1
    sub     r5,r7,r10               ; slot: low word of n - d
    bne     r4,r6,.Lsub             ; nh > dh: n > d
    sub     r4,r6,r11               ; slot: high word of n - d, before the borrow
    nop
    blo     r5,r7,.Lnext            ; nh = dh and nl < dl
    nop
    nop
.Lsub:
    blosq   r5,r7,1f                ; borrow from the low word: run the slots
    addi    r11,#-1,r11
    nop
1:  mov     r10,r5
    mov     r11,r4                  ; n -= d
    addi    r3,#1,r3                ; q |= 1
.Lnext:
    sh      r7,r6,r7,#1             ; d >>= 1
    lsr     r6,r6,#1
    bne     r9,r0,.Lloop
    addi    r9,#-1,r9               ; slot
    nop                             ; slot
.Lret:
    ret
    nop
    nop

; r1 = number of leading zeros of r10:r11 (not 0).  Clobbers r10, r11;
; returns through r8.
.Lclz64:
    bne     r10,r0,1f
    mov     r0,r1                   ; slot
    nop                             ; slot
    mov     r11,r10                 ; high word 0: count the low word
    addi    r0,#32,r1
1:  lsr     r10,r11,#16
    beqsq   r11,r0,1f               ; top 16 bits clear: run the slots
    addi    r1,#16,r1
    lsl     r10,r10,#16
1:  lsr     r10,r11,#24
    beqsq   r11,r0,1f
    addi    r1,#8,r1
    lsl     r10,r10,#8
1:  lsr     r10,r11,#28
    beqsq   r11,r0,1f
    addi    r1,#4,r1
    lsl     r10,r10,#4
1:  lsr     r10,r11,#30
    beqsq   r11,r0,1f
    addi    r1,#2,r1
    lsl     r10,r10,#2
1:  lsr     r10,r11,#31             ; top bit
    jspci   r8,#0,r0                ; return
    sub     r1,r11,r1               ; slot: + 1 if the top bit is clear
    addi    r1,#1,r1                ; slot
    .size   __udivdi3,.-__udivdi3

    .globl  __umoddi3
    .type   __umoddi3,@function
__umoddi3:                          ; r2:r3 = r4:r5 % r6:r7
    mov     r31,r15
    call    __udivdi3
    nop
    nop
    jspci   r15,#0,r0               ; return
    mov     r4,r2                   ; slot: the remainder
    mov     r5,r3                   ; slot
    .size   __umoddi3,.-__umoddi3

; |n| and |d| for the signed versions: r12 = sign of n, r13 = sign of the
; quotient (both 0 or -1).  A 64-bit negation is
;   hi = -hi - (lo != 0), lo = -lo
; where the squashed slots skip the borrow (and -0) when lo = 0.

    .globl  __divdi3
    .type   __divdi3,@function
__divdi3:                           ; r2:r3 = r4:r5 / r6:r7
    mov     r31,r15
    bge     r4,r0,1f
    asr     r4,r12,#31              ; slot: sign of n
    asr     r6,r13,#31              ; slot: sign of d
    sub     r0,r4,r4                ; n = -n
    bnesq   r5,r0,1f
    addi    r4,#-1,r4
    sub     r0,r5,r5
1:  bge     r6,r0,1f
    xor     r12,r13,r13             ; slot: sign of the quotient
    nop
    sub     r0,r6,r6                ; d = -d
    bnesq   r7,r0,1f
    addi    r6,#-1,r6
    sub     r0,r7,r7
1:  call    __udivdi3
    nop
    nop
    beq     r13,r0,1f
    nop
    nop
    sub     r0,r2,r2                ; q = -q
    bnesq   r3,r0,1f
    addi    r2,#-1,r2
    sub     r0,r3,r3
1:  jspci   r15,#0,r0               ; return
    nop
    nop
    .size   __divdi3,.-__divdi3

    .globl  __moddi3
    .type   __moddi3,@function
__moddi3:                           ; r2:r3 = r4:r5 % r6:r7
    mov     r31,r15
    bge     r4,r0,1f
    asr     r4,r12,#31              ; slot: sign of n
    nop
    sub     r0,r4,r4                ; n = -n
    bnesq   r5,r0,1f
    addi    r4,#-1,r4
    sub     r0,r5,r5
1:  bge     r6,r0,1f
    nop
    nop
    sub     r0,r6,r6                ; d = -d
    bnesq   r7,r0,1f
    addi    r6,#-1,r6
    sub     r0,r7,r7
1:  call    __udivdi3
    nop
    nop
    mov     r4,r2                   ; the remainder
    beq     r12,r0,1f
    mov     r5,r3                   ; slot
    nop                             ; slot
    sub     r0,r2,r2                ; r = -r
    bnesq   r3,r0,1f
    addi    r2,#-1,r2
    sub     r0,r3,r3
1:  jspci   r15,#0,r0               ; return
    nop
    nop
    .size   __moddi3,.-__moddi3
