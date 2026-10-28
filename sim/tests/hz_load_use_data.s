; P1: loaded value used as store data.
; EXIT: 125
; STDERR: load-use hazard (P1): st -8[r29],r4 reads r4
_start:
    ld    -16[r29],r4
    st    -8[r29],r4
    exit  #0
