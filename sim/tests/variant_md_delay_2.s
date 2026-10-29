; --variant=md-delay-2: P4 also applies two instructions apart.
; ARGS: --variant=md-delay-2
; EXIT: 125
; STDERR: MD hazard at distance 2 (variant md-delay-2): mstart r5,r6
_start:
    movtos r4,md
    nop
    mstart r5,r6
    exit  #0
