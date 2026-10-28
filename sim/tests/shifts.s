; sh (funnel shift), asr, rotlb, rotlcb and the lsl/lsr aliases (spec §5).
; STDERR-EMPTY
_start:
    li    0x89ABCDEF,r4
    li    0x01234567,r5
    sh    r4,r5,r6,#8         ; low 32 of (r5:r4) >> 8
    expect r6,0x6789ABCD
    sh    r4,r5,r6,#1
    expect r6,0xC4D5E6F7
    sh    r4,r5,r6,#31
    expect r6,0x02468ACF
    sh    r4,r5,r6,#32        ; e = 0: Src2 itself
    expect r6,0x01234567
    sh    r4,r5,r6,#24        ; e = 8 (bbb=2, dddd=0001)
    expect r6,0x23456789
    sh    r4,r5,r6,#7         ; e = 25 (bbb=6, dddd=0010)
    expect r6,0xCF13579B
    lsl   r5,r6,#4            ; sh r0,r5,r6,#28
    expect r6,0x12345670
    lsl   r5,r6,#0            ; sh r0,r5,r6,#32
    expect r6,0x01234567
    lsl   r5,r6,#31
    expect r6,0x80000000
    lsr   r4,r6,#4            ; sh r4,r0,r6,#4
    expect r6,0x089ABCDE
    lsr   r4,r6,#32
    expect r6,0
    lsr   r4,r6,#31
    expect r6,1
    asr   r4,r6,#4
    expect r6,0xF89ABCDE
    asr   r4,r6,#31
    expect r6,0xFFFFFFFF
    asr   r4,r6,#32
    expect r6,0xFFFFFFFF
    asr   r5,r6,#32
    expect r6,0
    asr   r5,r6,#1
    expect r6,0x0091A2B3
    li    0xAB01CD23,r7       ; manual §4.4.14 and §4.4.15 examples
    addi  r0,#0x51,r8
    rotlb r7,r8,r9
    expect r9,0x01CD23AB
    rotlcb r7,r8,r9
    expect r9,0xCD23AB01
    rotlb r7,r0,r9            ; by 0
    expect r9,0xAB01CD23
    rotlcb r7,r0,r9           ; by 3
    expect r9,0x23AB01CD
    addi  r0,#3,r8
    rotlb r7,r8,r9
    expect r9,0x23AB01CD
    addi  r0,#2,r8
    rotlb r7,r8,r9
    expect r9,0xCD23AB01
    exit  #0
