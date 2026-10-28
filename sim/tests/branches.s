; All six branch conditions, taken and not taken, signed and unsigned, and
; the two delay slots that always execute (spec §4).  r9 counts executed
; slot instructions.
; STDERR-EMPTY
_start:
    addi  r0,#-1,r4           ; 0xFFFFFFFF: signed -1, unsigned max
    addi  r0,#1,r5
    addi  r0,#0,r9

    beq   r5,r5,1f            ; taken
    addi  r9,#1,r9
    addi  r9,#1,r9
    exit  #101
1:  bne   r4,r5,2f            ; taken
    addi  r9,#1,r9
    addi  r9,#1,r9
    exit  #102
2:  blt   r4,r5,3f            ; -1 < 1 signed: taken
    addi  r9,#1,r9
    addi  r9,#1,r9
    exit  #103
3:  bhs   r4,r5,4f            ; 0xFFFFFFFF >= 1 unsigned: taken
    addi  r9,#1,r9
    addi  r9,#1,r9
    exit  #104
4:  bge   r5,r4,5f            ; 1 >= -1 signed: taken
    addi  r9,#1,r9
    addi  r9,#1,r9
    exit  #105
5:  blo   r5,r4,6f            ; 1 < 0xFFFFFFFF unsigned: taken
    addi  r9,#1,r9
    addi  r9,#1,r9
    exit  #106
6:  expect r9,12
    ; not taken: fall through after the slots, which still execute
    beq   r4,r5,bad
    addi  r9,#1,r9
    addi  r9,#1,r9
    bne   r5,r5,bad
    addi  r9,#1,r9
    addi  r9,#1,r9
    blt   r5,r4,bad           ; 1 < -1: no
    addi  r9,#1,r9
    addi  r9,#1,r9
    bhs   r5,r4,bad           ; 1 >= 0xFFFFFFFF unsigned: no
    addi  r9,#1,r9
    addi  r9,#1,r9
    bge   r4,r5,bad           ; -1 >= 1: no
    addi  r9,#1,r9
    addi  r9,#1,r9
    blo   r4,r5,bad           ; 0xFFFFFFFF < 1 unsigned: no
    addi  r9,#1,r9
    addi  r9,#1,r9
    expect r9,24
    ; equal operands
    bge   r5,r5,7f
    nop
    nop
    exit  #107
7:  bhs   r5,r5,8f
    nop
    nop
    exit  #108
8:  blt   r5,r5,bad
    nop
    nop
    blo   r5,r5,bad
    nop
    nop
    ; INT_MIN vs INT_MAX (subtraction overflows: N xor V)
    li    0x80000000,r6
    li    0x7FFFFFFF,r7
    blt   r6,r7,9f
    nop
    nop
    exit  #109
9:  bge   r7,r6,10f
    nop
    nop
    exit  #110
10: blo   r7,r6,11f
    nop
    nop
    exit  #111
11: ; pseudo forms with swapped operands
    bgt   r5,r4,12f           ; blt r4,r5
    nop
    nop
    exit  #112
12: bhi   r4,r5,13f           ; blo r5,r4
    nop
    nop
    exit  #113
13: ; backward branch: count down a loop
    addi  r0,#5,r10
    addi  r0,#0,r11
loop:
    addi  r10,#-1,r10
    bne   r10,r0,loop
    addi  r11,#1,r11          ; slot 1, runs every iteration
    nop
    expect r11,5
    b     done
    nop
    nop
bad:
    exit  #99
done:
    exit  #0
