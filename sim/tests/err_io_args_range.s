; The argv block must fit in RAM.
; EXIT: 125
; STDERR: is outside RAM
_start:
    li    #0x1FFFF8,r6
    st    -65496[r0],r6
    exit  #0
