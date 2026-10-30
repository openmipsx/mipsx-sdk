; --variant=rotlcb: Func 0x080 is the manual's rotlcb, Dest = Src1
; rotated left by (~Src2 & 3) bytes, not shlv (spec §5). Examples from
; manual §4.4.15. shav is unchanged.
; ARGS: --variant=rotlcb
; STDERR-EMPTY
_start:
    li    0xAB01CD23,r7
    addi  r0,#0x51,r8
    rotlcb r7,r8,r9           ; by 2
    expect r9,0xCD23AB01
    rotlcb r7,r0,r9           ; by 3
    expect r9,0x23AB01CD
    addi  r0,#-4,r8
    shlv  r7,r8,r9            ; the same word: by 3, no count check
    expect r9,0x23AB01CD
    addi  r0,#64,r8
    shlv  r7,r8,r9            ; 64: by 3
    expect r9,0x23AB01CD
    li    0x80000010,r4
    addi  r0,#-4,r5
    shav  r4,r5,r6
    expect r6,0xF8000001
    exit  #0
