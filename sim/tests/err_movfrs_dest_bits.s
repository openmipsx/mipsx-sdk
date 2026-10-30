; movfrs with bits 16-12 set: the field is 0 on the hardware (spec §2, §6;
; devices b6cdbcb), so the old encoding of movfrs psw,r2 is rejected.
; EXIT: 125
; ARGS: --hazards=off
; STDERR: undefined instruction 0xd8002001: movfrs with non-zero bits 16-12 (Dest is bits 21-17)
_start:
    .word 0xD8002001
