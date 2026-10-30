; Without EF_MIPSX_VSHIFT the shifts by a register amount are errors
; (abi §11.2); the byte and halfword memory ops still run.
; ELF: flags=1
; EXIT: 125
; STDERR: shlv is an ES3890 variable shift, but the program's e_flags lack EF_MIPSX_VSHIFT
_start:
    ldb   -16[r29],r4         ; EF_MIPSX_ES3890 is enough for this
    nop
    shlv  r4,r5,r6
    exit  #0
