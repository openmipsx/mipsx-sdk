; P1 through Src2.
; EXIT: 125
; STDERR: load-use hazard (P1): sub r5,r4,r6 reads r4
_start:
    ld    -16[r29],r4
    sub   r5,r4,r6
    exit  #0
