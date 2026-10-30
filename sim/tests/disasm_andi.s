; --disassemble: OP 001 words are andi Src1,#imm,Dest with Dest in the
; Src2 field, bits 21-17, and a sign-extended imm17, except 0xCFC00000,
; which is hsc (spec §6).
; ARGS: --disassemble
; STDOUT: _start:
; STDOUT: 00002000: c90c00ff  andi r4,#255,r6
; STDOUT: 00002004: c90dfffc  andi r4,#-4,r6
; STDOUT: 00002008: c94f0000  andi r5,#-65536,r7
; STDOUT: 0000200c: c8000000  andi r0,#0,r0
; STDOUT: 00002010: cfc00000  hsc
; STDOUT: 00002014: cfc00001  andi r31,#1,r0
_start:
    andi  r4,#0xFF,r6
    andi  r4,#-4,r6
    andi  r5,#-65536,r7
    .word 0xC8000000
    .word 0xCFC00000
    .word 0xCFC00001
