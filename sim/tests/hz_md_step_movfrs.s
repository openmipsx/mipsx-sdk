; P4: movfrs md right after a step (as in the manual's division routine).
; EXIT: 125
; STDERR: MD hazard (P4): movfrs md,r6 right after a multiply or divide step
_start:
    dstep r3,r5,r3
    movfrs md,r6
    exit  #0
