; --disassemble: 0xD8040001 is movfrs psw into r2, with Dest in the Src2
; field, bits 21-17, and bits 16-12 = 0 (spec §2, §6; devices b6cdbcb).
; ARGS: --disassemble
; STDOUT: _start:
; STDOUT: 00002000: d8040001  movfrs psw,r2
; STDOUT: 00002004: d8040001  movfrs psw,r2
; STDOUT: 00002008: d83e0004  movfrs pcm4,r31
_start:
    .word 0xD8040001
    movfrs psw,r2
    movfrs pcm4,r31
