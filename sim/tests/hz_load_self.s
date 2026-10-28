; P2: a load overwrites its own address register.
; EXIT: 125
; STDERR: load overwrites its own address register r4 (P2): ld 0[r4],r4
_start:
    la    word,r4
    ld    0[r4],r4
    exit  #0
word:
    .word 0
