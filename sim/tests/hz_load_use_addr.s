; P1: loaded value used as an address.
; EXIT: 125
; STDERR: load-use hazard (P1): ld 0[r4],r5 reads r4
_start:
    ld    -16[r29],r4
    ld    0[r4],r5
    exit  #0
