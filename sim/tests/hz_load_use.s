; P1: the instruction after a load reads its destination (Src1).
; EXIT: 125
; STDERR: error: pc 0x00002008 <_start+0x8>: load-use hazard (P1): mov r4,r5 reads r4, loaded by the previous instruction at 0x00002004 <_start+0x4>
_start:
    nop
    ld    -16[r29],r4
    add   r4,r0,r5
    exit  #0
