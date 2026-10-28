; P5: misaligned halfword store.
; EXIT: 125
; STDERR: misaligned 2-byte access to 0x0000201d (P5)
_start:
    la    word,r4
    sth   1[r4],r5
    exit  #0
    .word 0
word:
    .word 0
