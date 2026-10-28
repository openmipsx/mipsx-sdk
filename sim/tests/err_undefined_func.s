; Undefined compute function.
; EXIT: 125
; ARGS: --hazards=off
; STDERR: undefined instruction 0x60000018: undefined compute function (OP 100)
_start:
    .word 0x60000018
