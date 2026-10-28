; P2 as a warning: the load completes.
; ARGS: -w
; STDERR: warning: pc 0x00002010 <_start+0x10>: load overwrites its own address register r4 (P2)
_start:
    la    word,r4
    nop
    ld    0[r4],r4
    nop
    expect r4,0x1234
    exit  #0
word:
    .word 0x1234
