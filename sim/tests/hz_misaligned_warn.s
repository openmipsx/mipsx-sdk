; P5 as a warning: the hardware drops the low address bits.
; ARGS: --hazards=warn
; STDERR: misaligned 4-byte access
_start:
    la    word,r4
    ld    3[r4],r5
    nop
    expect r5,0xCAFEF00D
    exit  #0
word:
    .word 0xCAFEF00D
