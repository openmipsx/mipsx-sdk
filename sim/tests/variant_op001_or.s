; --variant=op001-or: compute-immediate OP 001 is Dest = Src1 |
; SignExtend(imm17), not & (spec §6). hsc is unchanged.
; ARGS: --variant=op001-or
; STDERR-EMPTY
_start:
    li    0x87654321,r5
    andi  r5,#0xFF,r6
    expect r6,0x876543FF
    andi  r5,#-4,r6
    expect r6,0xFFFFFFFD
    andi  r0,#0x10,r6
    expect r6,0x10
    exit  #0
