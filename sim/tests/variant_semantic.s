; --variant: the semantic variants change what instructions do
; (sim/README.md, "Variants").
; ARGS: --variant=ldb-swap,ldh-swap,bic-swap --variant=shift32-zero,squash-taken,dstep-borrow
; STDERR-EMPTY
_start:
    li    0x8899AABB,r5
    st    -16[r29],r5
    ldbu  -16[r29],r6         ; ldb-swap: sign-extends
    nop
    expect r6,0xFFFFFF88
    ldb   -16[r29],r6         ; ldb-swap: zero-extends
    nop
    expect r6,0x88
    ldhu  -16[r29],r6         ; ldh-swap: sign-extends
    nop
    expect r6,0xFFFF8899
    ldh   -16[r29],r6         ; ldh-swap: zero-extends
    nop
    expect r6,0x8899
    li    0x0F0F00FF,r4
    bic   r4,r5,r6            ; bic-swap: r4 & ~r5
    expect r6,0x07060044
    li    0x12345678,r4
    sh    r4,r5,r6,#32        ; shift32-zero: Src1, not Src2
    expect r6,0x12345678
    asr   r5,r6,#32           ; shift32-zero: unchanged
    expect r6,0x8899AABB
    addi  r0,#0,r9
    beqsq r4,r4,1f            ; squash-taken: taken, slots squashed
    addi  r9,#1,r9
    addi  r9,#2,r9
    exit  #101
1:  expect r9,0
    bnesq r4,r4,1f            ; squash-taken: not taken, slots execute
    addi  r9,#1,r9
    addi  r9,#2,r9
    expect r9,3
1:  movtos r0,md
    li    0x80000000,r7
    li    1,r8
    dstep r7,r8,r7            ; dstep-borrow: 0x100000000 >= 1, subtract
    nop
    movfrs md,r10
    expect r7,0xFFFFFFFF
    expect r10,1
    exit  #0
