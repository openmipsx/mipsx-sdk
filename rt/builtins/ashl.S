; ashl.S: __ashlsi3 and __ashldi3, shift left by a variable amount.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Run-time helpers for the code generator (work package S12; see
; rt/builtins/README.md).  Names and arguments as in libgcc and
; compiler-rt:
;
;   int       __ashlsi3(int a, int n)        r2    = r4 << (n & 31),     n in r5
;   long long __ashldi3(long long a, int n)  r2:r3 = r4:r5 << (n & 63), n in r6
;
; Only the low 5 (6) bits of the amount are used, so an out-of-range
; amount (undefined in C) gives a defined result.
;
; MIPS-X has only immediate shifts, so both routines jump into a table of
; 32 entries, one per amount k = 0..31.  Each entry is four words:
;
;   ret                     ; jspci r31,#0,r0
;   <high word op>          ; delay slot 1
;   <low word op>           ; delay slot 2
;   nop                     ; padding, never executed
;
; The table address comes from a jspci to the next instruction, which
; writes its own word address + 3 to r1 (abi §5.1).  The dispatch
; immediates (#15 and #4 below) are the distances in words from that
; address to .Ltable; they must change if code is added in between.
; Entry k sets r2 = high word of (r4:r5) << k (a funnel shift) and
; r3 = r5 << k.  __ashlsi3 clears r5 first; its r3 result is junk.
;
; Clobbers (a private guarantee the backend may rely on, see the README):
;   __ashlsi3: r1-r3, r5
;   __ashldi3: r1-r5
; Cycles, including the return: __ashlsi3 10, __ashldi3 14, for any amount.

    .text
    .globl  __ashldi3
    .type   __ashldi3,@function
__ashldi3:
    jspci   r0,#%call(.Ldi_pc),r1   ; r1 = word address of .Ldi_pc
    lsl     r6,r2,#27               ; slot 1
    lsr     r2,r2,#25               ; slot 2: r2 = 4 * (n & 31), entry offset
.Ldi_pc:
    lsl     r6,r3,#26               ; bit 5 of n to the sign bit
    add     r1,r2,r1
    bltsq   r3,r0,.Ldi_go           ; n & 32: run the slots, else squash them
    mov     r5,r4                   ; n >= 32: high = low
    mov     r0,r5                   ; low = 0
.Ldi_go:
    jspci   r1,#15,r0               ; .Ltable = .Ldi_pc + 15 words
    nop
    nop
    .size   __ashldi3,.-__ashldi3

    .globl  __ashlsi3
    .type   __ashlsi3,@function
__ashlsi3:
    jspci   r0,#%call(.Lsi_pc),r1   ; r1 = word address of .Lsi_pc
    lsl     r5,r2,#27               ; slot 1
    lsr     r2,r2,#25               ; slot 2: r2 = 4 * (n & 31)
.Lsi_pc:
    add     r1,r2,r1
    jspci   r1,#4,r0                ; .Ltable = .Lsi_pc + 4 words
    mov     r0,r5                   ; slot: low word 0, so r2 = r4 << k
    nop

; Entry k: r4:r5 is the (possibly pre-shifted) 64-bit operand.
.Ltable:
    ret                             ; k = 0
    mov     r4,r2
    mov     r5,r3
    nop
    ret                             ; k = 1
    sh      r5,r4,r2,#31
    lsl     r5,r3,#1
    nop
    ret                             ; k = 2
    sh      r5,r4,r2,#30
    lsl     r5,r3,#2
    nop
    ret                             ; k = 3
    sh      r5,r4,r2,#29
    lsl     r5,r3,#3
    nop
    ret                             ; k = 4
    sh      r5,r4,r2,#28
    lsl     r5,r3,#4
    nop
    ret                             ; k = 5
    sh      r5,r4,r2,#27
    lsl     r5,r3,#5
    nop
    ret                             ; k = 6
    sh      r5,r4,r2,#26
    lsl     r5,r3,#6
    nop
    ret                             ; k = 7
    sh      r5,r4,r2,#25
    lsl     r5,r3,#7
    nop
    ret                             ; k = 8
    sh      r5,r4,r2,#24
    lsl     r5,r3,#8
    nop
    ret                             ; k = 9
    sh      r5,r4,r2,#23
    lsl     r5,r3,#9
    nop
    ret                             ; k = 10
    sh      r5,r4,r2,#22
    lsl     r5,r3,#10
    nop
    ret                             ; k = 11
    sh      r5,r4,r2,#21
    lsl     r5,r3,#11
    nop
    ret                             ; k = 12
    sh      r5,r4,r2,#20
    lsl     r5,r3,#12
    nop
    ret                             ; k = 13
    sh      r5,r4,r2,#19
    lsl     r5,r3,#13
    nop
    ret                             ; k = 14
    sh      r5,r4,r2,#18
    lsl     r5,r3,#14
    nop
    ret                             ; k = 15
    sh      r5,r4,r2,#17
    lsl     r5,r3,#15
    nop
    ret                             ; k = 16
    sh      r5,r4,r2,#16
    lsl     r5,r3,#16
    nop
    ret                             ; k = 17
    sh      r5,r4,r2,#15
    lsl     r5,r3,#17
    nop
    ret                             ; k = 18
    sh      r5,r4,r2,#14
    lsl     r5,r3,#18
    nop
    ret                             ; k = 19
    sh      r5,r4,r2,#13
    lsl     r5,r3,#19
    nop
    ret                             ; k = 20
    sh      r5,r4,r2,#12
    lsl     r5,r3,#20
    nop
    ret                             ; k = 21
    sh      r5,r4,r2,#11
    lsl     r5,r3,#21
    nop
    ret                             ; k = 22
    sh      r5,r4,r2,#10
    lsl     r5,r3,#22
    nop
    ret                             ; k = 23
    sh      r5,r4,r2,#9
    lsl     r5,r3,#23
    nop
    ret                             ; k = 24
    sh      r5,r4,r2,#8
    lsl     r5,r3,#24
    nop
    ret                             ; k = 25
    sh      r5,r4,r2,#7
    lsl     r5,r3,#25
    nop
    ret                             ; k = 26
    sh      r5,r4,r2,#6
    lsl     r5,r3,#26
    nop
    ret                             ; k = 27
    sh      r5,r4,r2,#5
    lsl     r5,r3,#27
    nop
    ret                             ; k = 28
    sh      r5,r4,r2,#4
    lsl     r5,r3,#28
    nop
    ret                             ; k = 29
    sh      r5,r4,r2,#3
    lsl     r5,r3,#29
    nop
    ret                             ; k = 30
    sh      r5,r4,r2,#2
    lsl     r5,r3,#30
    nop
    ret                             ; k = 31
    sh      r5,r4,r2,#1
    lsl     r5,r3,#31
    nop
    .size   __ashlsi3,.-__ashlsi3
