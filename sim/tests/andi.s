; andi: every compute-immediate OP 001 word except 0xCFC00000 is
; andi Src1,#imm,Dest, Dest (Src2 field, bits 21-17) = Src1 &
; SignExtend(imm17), sign bit 16 (spec §6, Observed 2026-10-30).
; STDERR-EMPTY
_start:
    li    0x12345678,r4
    andi  r4,#0xFF,r6
    expect r6,0x00000078
    andi  r4,#-4,r6           ; clears bits 1-0 only
    expect r6,0x12345678
    li    0x87654321,r5
    andi  r5,#-4,r6
    expect r6,0x87654320
    andi  r5,#-2,r6
    expect r6,0x87654320
    andi  r5,#-65536,r6       ; field 0x10000: masks with 0xFFFF0000
    expect r6,0x87650000
    .word 0xC94F0000          ; andi r5,#0x10000 field,r7, encoded by hand
    expect r7,0x87650000
    .word 0xC90C00FF          ; andi r4,#0xFF,r6, encoded by hand
    expect r6,0x00000078
    andi  r4,#65535,r6        ; largest positive immediate
    expect r6,0x00005678
    andi  r4,#0,r6
    expect r6,0
    expect r4,0x12345678      ; Src1 is not written when Dest differs
    andi  r5,#0xF0F0,r5       ; Dest = Src1
    expect r5,0x00004020
    andi  r4,#-1,r0           ; Dest = r0: no write
    expect r0,0
    .word 0xC8000000          ; andi r0,#0,r0: a no-op, not a stop
    exit  #0
