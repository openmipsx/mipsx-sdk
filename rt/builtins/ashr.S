; ashr.S: __ashrsi3 and __ashrdi3, arithmetic shift right by a variable amount.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Run-time helpers for the code generator (work package S12; see
; rt/builtins/README.md).  Names and arguments as in libgcc and
; compiler-rt:
;
;   int       __ashrsi3(int a, int n)        r2    = r4 >> (n & 31),     n in r5
;   long long __ashrdi3(long long a, int n)  r2:r3 = r4:r5 >> (n & 63), n in r6
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
; Entry k sets r3 = low word of (r4:r5) >> k and r2 = r4 >> k
; (arithmetic).  For __ashrsi3 the r3 result is junk.
;
; Clobbers (a private guarantee the backend may rely on, see the README):
;   __ashrsi3: r1-r3
;   __ashrdi3: r1-r5
; Cycles, including the return: __ashrsi3 10, __ashrdi3 14, for any amount.

    .text
    .globl  __ashrdi3
    .type   __ashrdi3,@function
__ashrdi3:
    jspci   r0,#%call(.Ldi_pc),r1   ; r1 = word address of .Ldi_pc
    lsl     r6,r2,#27               ; slot 1
    lsr     r2,r2,#25               ; slot 2: r2 = 4 * (n & 31), entry offset
.Ldi_pc:
    lsl     r6,r3,#26               ; bit 5 of n to the sign bit
    add     r1,r2,r1
    bltsq   r3,r0,.Ldi_go           ; n & 32: run the slots, else squash them
    mov     r4,r5                   ; n >= 32: low = high
    asr     r4,r4,#31               ; high = sign
.Ldi_go:
    jspci   r1,#15,r0               ; .Ltable = .Ldi_pc + 15 words
    nop
    nop
    .size   __ashrdi3,.-__ashrdi3

    .globl  __ashrsi3
    .type   __ashrsi3,@function
__ashrsi3:
    jspci   r0,#%call(.Lsi_pc),r1   ; r1 = word address of .Lsi_pc
    lsl     r5,r2,#27               ; slot 1
    lsr     r2,r2,#25               ; slot 2: r2 = 4 * (n & 31)
.Lsi_pc:
    add     r1,r2,r1
    jspci   r1,#4,r0                ; .Ltable = .Lsi_pc + 4 words
    nop                             ; slot
    nop

; Entry k: r4:r5 is the (possibly pre-shifted) 64-bit operand.
.Ltable:
    ret                             ; k = 0
    mov     r5,r3
    mov     r4,r2
    nop
    ret                             ; k = 1
    sh      r5,r4,r3,#1
    asr     r4,r2,#1
    nop
    ret                             ; k = 2
    sh      r5,r4,r3,#2
    asr     r4,r2,#2
    nop
    ret                             ; k = 3
    sh      r5,r4,r3,#3
    asr     r4,r2,#3
    nop
    ret                             ; k = 4
    sh      r5,r4,r3,#4
    asr     r4,r2,#4
    nop
    ret                             ; k = 5
    sh      r5,r4,r3,#5
    asr     r4,r2,#5
    nop
    ret                             ; k = 6
    sh      r5,r4,r3,#6
    asr     r4,r2,#6
    nop
    ret                             ; k = 7
    sh      r5,r4,r3,#7
    asr     r4,r2,#7
    nop
    ret                             ; k = 8
    sh      r5,r4,r3,#8
    asr     r4,r2,#8
    nop
    ret                             ; k = 9
    sh      r5,r4,r3,#9
    asr     r4,r2,#9
    nop
    ret                             ; k = 10
    sh      r5,r4,r3,#10
    asr     r4,r2,#10
    nop
    ret                             ; k = 11
    sh      r5,r4,r3,#11
    asr     r4,r2,#11
    nop
    ret                             ; k = 12
    sh      r5,r4,r3,#12
    asr     r4,r2,#12
    nop
    ret                             ; k = 13
    sh      r5,r4,r3,#13
    asr     r4,r2,#13
    nop
    ret                             ; k = 14
    sh      r5,r4,r3,#14
    asr     r4,r2,#14
    nop
    ret                             ; k = 15
    sh      r5,r4,r3,#15
    asr     r4,r2,#15
    nop
    ret                             ; k = 16
    sh      r5,r4,r3,#16
    asr     r4,r2,#16
    nop
    ret                             ; k = 17
    sh      r5,r4,r3,#17
    asr     r4,r2,#17
    nop
    ret                             ; k = 18
    sh      r5,r4,r3,#18
    asr     r4,r2,#18
    nop
    ret                             ; k = 19
    sh      r5,r4,r3,#19
    asr     r4,r2,#19
    nop
    ret                             ; k = 20
    sh      r5,r4,r3,#20
    asr     r4,r2,#20
    nop
    ret                             ; k = 21
    sh      r5,r4,r3,#21
    asr     r4,r2,#21
    nop
    ret                             ; k = 22
    sh      r5,r4,r3,#22
    asr     r4,r2,#22
    nop
    ret                             ; k = 23
    sh      r5,r4,r3,#23
    asr     r4,r2,#23
    nop
    ret                             ; k = 24
    sh      r5,r4,r3,#24
    asr     r4,r2,#24
    nop
    ret                             ; k = 25
    sh      r5,r4,r3,#25
    asr     r4,r2,#25
    nop
    ret                             ; k = 26
    sh      r5,r4,r3,#26
    asr     r4,r2,#26
    nop
    ret                             ; k = 27
    sh      r5,r4,r3,#27
    asr     r4,r2,#27
    nop
    ret                             ; k = 28
    sh      r5,r4,r3,#28
    asr     r4,r2,#28
    nop
    ret                             ; k = 29
    sh      r5,r4,r3,#29
    asr     r4,r2,#29
    nop
    ret                             ; k = 30
    sh      r5,r4,r3,#30
    asr     r4,r2,#30
    nop
    ret                             ; k = 31
    sh      r5,r4,r3,#31
    asr     r4,r2,#31
    nop
    .size   __ashrsi3,.-__ashrsi3
