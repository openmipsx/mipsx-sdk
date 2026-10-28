; Squashing branches (SQ = 1): the slots execute only if the branch is
; taken (spec §4).  Squashed slots cost cycles but have no effect.
; STDERR-EMPTY
_start:
    addi  r0,#1,r4
    addi  r0,#0,r9
    beqsq r4,r4,1f            ; taken: slots execute
    addi  r9,#1,r9
    addi  r9,#2,r9
    exit  #101
1:  expect r9,3
    bnesq r4,r4,bad           ; not taken: slots squashed
    addi  r9,#10,r9
    st    -65536[r0],r4       ; a squashed store does not print
    expect r9,3
    ; a squashed load does not write its register, and no load-use
    ; hazard is reported for squashed instructions
    addi  r0,#7,r5
    bltsq r4,r0,bad
    ld    0[r0],r5
    add   r5,r5,r5
    expect r5,7
    ; squashed slots of a branch that falls through into a loop
    addi  r0,#3,r10
    addi  r0,#0,r11
loop:
    addi  r11,#1,r11
    addi  r10,#-1,r10
    bnesq r10,r0,loop
    addi  r12,#1,r12          ; only on taken iterations (2 of 3)
    nop
    expect r11,3
    expect r12,2
    exit  #0
bad:
    exit  #99
