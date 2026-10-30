; Shifts by a signed count in Src2 (spec §5, Observed 2026-10-30): if
; Src2 >= 0, Dest = Src1 << Src2, else Dest = Src1 >> -Src2, shifted in
; with sign bits by shav (Func 0x180) and zeros by shlv (Func 0x080).
; STDERR-EMPTY
_start:
    li    0x80000010,r4
    addi  r0,#4,r5
    shav  r4,r5,r6
    expect r6,0x00000100
    addi  r0,#-4,r5
    shav  r4,r5,r6            ; arithmetic
    expect r6,0xF8000001
    shlv  r4,r5,r6            ; logical
    expect r6,0x08000001
    addi  r0,#4,r5
    shlv  r4,r5,r6
    expect r6,0x00000100
    addi  r0,#5,r7
    shav  r7,r0,r6            ; count 0
    expect r6,5
    shlv  r7,r0,r6
    expect r6,5
    addi  r0,#1,r7
    addi  r0,#31,r5
    shav  r7,r5,r6            ; largest left count
    expect r6,0x80000000
    li    0x80000000,r7
    addi  r0,#-31,r5
    shav  r7,r5,r6            ; largest right count
    expect r6,0xFFFFFFFF
    shlv  r7,r5,r6
    expect r6,1
    li    0x40000000,r7
    shav  r7,r5,r6            ; positive value, arithmetic right
    expect r6,0
    addi  r0,#-30,r5
    shav  r7,r5,r6
    expect r6,1
    .word 0x490A6180          ; shav r4,r5,r6, encoded by hand
    expect r6,0xFFFFFFFE      ; 0x80000010 >> 30, arithmetic
    .word 0x490A6080          ; shlv r4,r5,r6, encoded by hand
    expect r6,2
    shav  r4,r5,r4            ; Dest = Src1
    expect r4,0xFFFFFFFE
    exit  #0
