; sh with a shift field whose dddd part is not one-hot.
; EXIT: 125
; STDERR: shift amount field dddd is not one-hot
_start:
    .word 0x48000203
