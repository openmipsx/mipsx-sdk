; Under --variant=rotlcb, Func 0x080 is the manual's rotate and needs no
; EF_MIPSX_VSHIFT.
; ARGS: --variant=rotlcb
; ELF: flags=1
; STDERR-EMPTY
_start:
    li    0xAB01CD23,r7
    addi  r0,#0x51,r8
    rotlcb r7,r8,r9           ; by 2
    expect r9,0xCD23AB01
    exit  #0
