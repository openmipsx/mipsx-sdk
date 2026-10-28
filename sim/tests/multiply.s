; Signed 32x32 multiplication with mstart and 31 msteps (manual App. IV).
; STDERR-EMPTY
_start:
    li    7,r4
    li    -3,r5
    call  mul
    nop
    nop
    expect r2,-21
    li    -5,r4
    li    -6,r5
    call  mul
    nop
    nop
    expect r2,30
    li    12345,r4
    li    678,r5
    call  mul
    nop
    nop
    expect r2,8369910
    li    0x10001,r4
    li    0x10001,r5
    call  mul
    nop
    nop
    expect r2,0x00020001      ; low 32 bits of 0x100020001
    li    0x80000000,r4
    li    -1,r5
    call  mul
    nop
    nop
    expect r2,0x80000000
    li    0,r4
    li    123,r5
    call  mul
    nop
    nop
    expect r2,0
    exit  #0

; r2 = r4 * r5 (r4 = multiplier, r5 = multiplicand)
mul:
    movtos r4,md
    nop                       ; P4: one instruction before using MD
    mstart r5,r2
    .rept 31
    mstep r2,r5,r2
    .endr
    ret
    nop
    nop
