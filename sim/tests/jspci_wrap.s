; Jump targets are word addresses modulo 2^30: bits 31-30 of
; Src1 + SignExtend(imm17) are ignored (spec §1, §6, "Target wrap").
; STDERR-EMPTY
_start:
    addi  r0,#0,r9
    ; base + offset has bit 30 set: lands on bits 29-0
    li    %w(t1)+0x40000000-100,r23
    jspci r23,#100,r0
    addi  r9,#1,r9
    nop
    exit  #101
t1:
    expect r9,1
    ; a vendor-style jump table entry: a negative 30-bit offset added to a
    ; code base register gives a sum with bit 30 set
    li    %w(base),r23
    li    0x40000000-(%w(base)-%w(t2)),r5
    add   r23,r5,r6
    jspci r6,#0,r31
    nop
    nop
    exit  #102
t2:
    expect r9,1
    ; bit 31 and bit 30 both set; the link value is still the jspci + 3
    li    %w(t3)+0xC0000000,r23
call3:
    jspci r23,#0,r31
    nop
    nop
    exit  #103
t3:
    expect r31,%w(call3)+3
    exit  #0
base:
    exit  #104
