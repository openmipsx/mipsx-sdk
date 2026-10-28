; Loads outside RAM and the I/O page are bus errors.
; EXIT: 125
; STDERR: load from unmapped address 0x10000000
_start:
    li    0x10000000,r4
    ld    0[r4],r5
    exit  #0
