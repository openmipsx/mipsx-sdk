; MD moves and the step instructions' effect on MD (spec §5, §6).
; STDERR-EMPTY
_start:
    li    0x80000001,r4
    movtos r4,md
    nop
    movfrs md,r5
    expect r5,0x80000001
    li    10,r6
    mstart r6,r7              ; MSB(MD) = 1: r7 = 0 - r6; MD <<= 1
    nop
    movfrs md,r5
    expect r7,-10
    expect r5,2
    li    3,r8
    mstep r8,r6,r7            ; MSB(MD) = 0: r7 = r8 << 1
    nop
    movfrs md,r5
    expect r7,6
    expect r5,4
    li    0xC0000000,r4
    movtos r4,md
    nop
    mstep r8,r6,r7            ; MSB(MD) = 1: r7 = (r8 << 1) + r6
    expect r7,16
    mstart r6,r7              ; MSB(MD) = 1 again (was bit 30)
    expect r7,-10
    mstart r6,r7              ; MSB(MD) = 0
    expect r7,0
    ; dstep: a = (src1 << 1) | MSB(MD); o = a - src2
    li    0x80000000,r4
    movtos r4,md
    nop
    li    2,r8
    li    5,r6
    dstep r8,r6,r7            ; a = 5, o = 0: r7 = 0, MD = (MD << 1) | 1
    nop
    movfrs md,r5
    expect r7,0
    expect r5,1
    li    4,r6
    dstep r8,r6,r7            ; a = 4, o = 0 -> r7 = 0, MD = 3
    expect r7,0
    li    9,r6
    dstep r8,r6,r7            ; a = 4, o < 0 -> r7 = a = 4, MD = 6
    nop
    movfrs md,r5
    expect r7,4
    expect r5,6
    exit  #0
