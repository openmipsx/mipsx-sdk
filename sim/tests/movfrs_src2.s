; movfrs keeps Dest in the Src2 field, bits 21-17, and bits 16-12 are 0
; (spec §2, §6, "movfrs destination"; devices b6cdbcb).  0xD8040001 is
; OP 011 compute-immediate, Spec 1 (PSW), r2 in bits 21-17: movfrs psw
; into r2.  The test assembler must produce the same word.
; STDERR-EMPTY
_start:
    li    0x12345678,r12      ; old Dest field (bits 16-12) of 0xD8040001
    .word 0xD8040001          ; movfrs psw,r2
    expect r2,0x155
    expect r12,0x12345678     ; r0..r31 by bits 16-12 untouched
    movfrs psw,r3
    expect r3,0x155
    ld    enc[r0],r4
    nop
    expect r4,0xD8040001
    exit  #0
enc:
    movfrs psw,r2
