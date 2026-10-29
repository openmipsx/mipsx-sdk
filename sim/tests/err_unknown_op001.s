; Compute-immediate OP 001 encodings other than hsc exist on the hardware
; but their function is unknown (spec §6): a stop, reported as unknown
; rather than undefined.
; EXIT: 125
; STDERR: unknown instruction 0xc8000000: compute-immediate OP 001 other than hsc
; NOT-STDERR: undefined instruction
_start:
    .word 0xC8000000
