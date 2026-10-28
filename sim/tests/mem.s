; Word, halfword and byte loads and stores; big-endian layout (spec §3).
; STDERR-EMPTY
_start:
    la    buf,r4
    li    0x8899AABB,r5
    st    0[r4],r5
    st    4[r4],r0
    ld    0[r4],r6
    nop
    expect r6,0x8899AABB
    ldbu  0[r4],r6            ; most significant byte first
    nop
    expect r6,0x88
    ldb   0[r4],r6
    nop
    expect r6,0xFFFFFF88
    ldbu  3[r4],r6
    nop
    expect r6,0xBB
    ldb   1[r4],r6
    nop
    expect r6,0xFFFFFF99
    ldhu  0[r4],r6
    nop
    expect r6,0x8899
    ldh   0[r4],r6
    nop
    expect r6,0xFFFF8899
    ldhu  2[r4],r6
    nop
    expect r6,0xAABB
    addi  r0,#0x1234,r7
    ldh   -6[r4],r6           ; buf - 8 + 2: the 0x1234 word below
    nop
    expect r6,0x1234
    addi  r0,#0x7F,r7
    stb   5[r4],r7
    li    0x0102ABCD,r7
    sth   6[r4],r7            ; stores the low 16 bits
    ld    4[r4],r6
    nop
    expect r6,0x007FABCD
    stb   4[r4],r7            ; low 8 bits
    ld    4[r4],r6
    nop
    expect r6,0xCD7FABCD
    ldb   7[r4],r6
    nop
    expect r6,0xFFFFFFCD
    ld    buf[r0],r6          ; absolute address through r0
    nop
    expect r6,0x8899AABB
    exit  #0
    .align 3
    .word 0x00001234
    .word 0
buf:
    .space 8
