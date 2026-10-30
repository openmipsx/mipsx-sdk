; --variant=op001-nop: compute-immediate OP 001 other than hsc leaves
; Dest unchanged (spec §6).
; ARGS: --variant=op001-nop
; STDERR-EMPTY
_start:
    li    0x87654321,r5
    li    0x12345678,r6
    andi  r5,#0xFF,r6
    expect r6,0x12345678
    andi  r5,#0,r5            ; Dest = Src1
    expect r5,0x87654321
    exit  #0
