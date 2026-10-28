; P1: loaded value compared by a branch.
; EXIT: 125
; STDERR: load-use hazard (P1): beq r0,r4,
_start:
    ld    -16[r29],r4
    beq   r0,r4,1f
    nop
    nop
1:  exit  #0
