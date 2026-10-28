; Through mipsx-run, a hazard still gives status 125.
; RUNNER:
; EXIT: 125
; STDERR: load-use hazard
_start:
    ld    -16[r29],r4
    add   r4,r4,r4
    exit  #0
