; P4: movtos md right after a step.
; EXIT: 125
; STDERR: MD hazard (P4): movtos r4,md right after a multiply or divide step
_start:
    mstep r3,r5,r3
    movtos r4,md
    exit  #0
