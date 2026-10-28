; An undefined instruction is always an error (branch condition 000).
; EXIT: 125
; STDERR: undefined instruction 0x00000000: branch condition 000 or 100 is undefined
_start:
    .word 0
