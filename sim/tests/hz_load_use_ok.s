; No hazard: one instruction between a load and its use, a load to r0, a
; load followed by an instruction that only writes the register, and the
; MD rules respected.
; STDERR-EMPTY
_start:
    addi  r0,#9,r4
    st    -16[r29],r4
    ld    -16[r29],r5
    nop
    expect r5,9
    ld    -16[r29],r0         ; r0 is never a hazard
    add   r0,r0,r6
    ld    -16[r29],r5
    addi  r0,#3,r5            ; overwrites r5; reads only r0
    expect r5,3
    ld    -16[r29],r5
    b     1f                  ; the load in front of a branch is fine if
    nop                       ; the branch does not read it
    nop
1:  expect r5,9
    exit  #0
