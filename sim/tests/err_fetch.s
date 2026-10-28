; Jumping outside RAM.
; EXIT: 125
; STDERR: instruction fetch from unmapped address 0x00400000
_start:
    li    0x100000,r4
    jspci r4,#0,r0
    nop
    nop
