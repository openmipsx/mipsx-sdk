; Unsigned division with 32 dsteps (manual App. IV): quotient in MD,
; remainder in the step register.
; STDERR-EMPTY
_start:
    li    100,r4
    li    7,r5
    call  div
    nop
    nop
    expect r2,14
    expect r3,2
    li    0x7FFFFFFF,r4
    li    3,r5
    call  div
    nop
    nop
    expect r2,0x2AAAAAAA
    expect r3,1
    li    1000000,r4
    li    1000,r5
    call  div
    nop
    nop
    expect r2,1000
    expect r3,0
    li    5,r4
    li    9,r5
    call  div
    nop
    nop
    expect r2,0
    expect r3,5
    exit  #0

; r2 = r4 / r5, r3 = r4 % r5 (both below 2^31)
div:
    movtos r4,md
    addi  r0,#0,r3
    .rept 32
    dstep r3,r5,r3
    .endr
    nop                       ; P4: no movfrs md right after a step
    movfrs md,r2
    ret
    nop
    nop
