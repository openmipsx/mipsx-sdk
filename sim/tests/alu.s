; Register-register compute instructions and addi (spec §5, §6).
; STDERR-EMPTY
_start:
    li    0x12345678,r4
    li    0x0F0F00FF,r5
    add   r4,r5,r6
    expect r6,0x21435777
    sub   r4,r5,r6
    expect r6,0x03255579
    sub   r5,r4,r6
    expect r6,0xFCDAAA87
    subnc r4,r5,r6            ; r4 + ~r5 = r4 - r5 - 1
    expect r6,0x03255578
    and   r4,r5,r6
    expect r6,0x02040078
    bic   r5,r4,r6            ; r4 & ~r5 (Src2 & ~Src1)
    expect r6,0x10305600
    not   r4,r6
    expect r6,0xEDCBA987
    or    r4,r5,r6
    expect r6,0x1F3F56FF
    xor   r4,r5,r6
    expect r6,0x1D3B5687
    mov   r4,r7
    expect r7,0x12345678
    add   r0,r4,r7            ; the other mov form
    expect r7,0x12345678
    li    0xFFFFFFFF,r8
    add   r8,r8,r9            ; wraps, no overflow trap
    expect r9,0xFFFFFFFE
    li    0x7FFFFFFF,r8
    addi  r8,#1,r9            ; signed overflow is silent (abi §13.3)
    expect r9,0x80000000
    addi  r0,#-65536,r10      ; immediate range limits
    expect r10,0xFFFF0000
    addi  r0,#65535,r10
    expect r10,0x0000FFFF
    addi  r4,#-1,r10
    expect r10,0x12345677
    add   r4,r5,r0            ; writes to r0 are discarded
    addi  r0,#5,r0
    expect r0,0
    nop
    exit  #0
