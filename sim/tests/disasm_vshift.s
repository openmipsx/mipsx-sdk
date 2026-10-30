; --disassemble: Func 0x180 is shav and Func 0x080 shlv, both
; Src1,Src2,Dest with Dest in bits 16-12 (spec §5). 0x080 disassembles
; as shlv whatever the variant.
; ARGS: --disassemble
; STDOUT: _start:
; STDOUT: 00002000: 490a6180  shav r4,r5,r6
; STDOUT: 00002004: 490a6080  shlv r4,r5,r6
; STDOUT: 00002008: 4fffe180  shav r31,r31,r30
; STDOUT: 0000200c: 49006168  asr r4,r6,#5
_start:
    shav  r4,r5,r6
    shlv  r4,r5,r6
    .word 0x4FFFE180
    asr   r4,r6,#5
