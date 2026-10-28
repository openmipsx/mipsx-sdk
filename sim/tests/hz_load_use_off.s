; With --hazards=off nothing is reported.
; ARGS: --hazards=off
; STDERR-EMPTY
_start:
    st    -16[r29],r0
    ld    -16[r29],r4
    addi  r4,#5,r5
    expect r5,5
    exit  #0
