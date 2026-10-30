; --variant=andi-zext: andi zero-extends imm17, Dest = Src1 & imm17,
; instead of sign-extending it (spec §6).
; ARGS: --variant=andi-zext
; STDERR-EMPTY
_start:
    li    0x87654321,r5
    andi  r5,#-4,r6           ; field 0x1FFFC
    expect r6,0x00014320
    andi  r5,#-65536,r6       ; field 0x10000
    expect r6,0x00010000
    andi  r5,#0xFF,r6         ; positive immediates are unchanged
    expect r6,0x21
    exit  #0
