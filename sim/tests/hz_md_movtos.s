; P4: mstart right after movtos md.
; EXIT: 125
; STDERR: MD hazard (P4): mstart r5,r6 right after movtos to md
_start:
    movtos r4,md
    mstart r5,r6
    exit  #0
