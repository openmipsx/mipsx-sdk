; P5: misaligned word load.
; EXIT: 125
; STDERR: misaligned 4-byte access to 0x0000201a (P5)
_start:
    la    word,r4
    ld    2[r4],r5
    exit  #0
word:
    .word 0
