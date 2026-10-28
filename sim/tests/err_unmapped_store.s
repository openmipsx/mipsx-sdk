; Stores just past the end of RAM.
; EXIT: 125
; STDERR: store to unmapped address 0x00200000
_start:
    li    0x00200000,r4
    st    0[r4],r5
    exit  #0
