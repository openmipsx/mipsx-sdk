; P4: movfrs md right after movtos md.
; EXIT: 125
; STDERR: MD hazard (P4): movfrs md,r6 right after movtos to md
_start:
    movtos r4,md
    movfrs md,r6
    exit  #0
