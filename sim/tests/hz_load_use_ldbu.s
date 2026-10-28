; P1 applies to the ES3890 byte and halfword loads as well.
; EXIT: 125
; STDERR: load-use hazard (P1): addi r4,#1,r4 reads r4
_start:
    ldbu  -16[r29],r4
    addi  r4,#1,r4
    exit  #0
