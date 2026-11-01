; Without --board, the SPA3000 addresses stay unmapped.
; EXIT: 125
; STDERR: load from unmapped address 0x1c000000
_start:
    li    0x1C000000,r4
    ld    0[r4],r5
    exit  #0
