; Without EF_MIPSX_ES3890 the byte and halfword loads are errors.
; ELF: flags=0
; EXIT: 125
; STDERR: ldb is an ES3890 instruction, but the program's e_flags lack EF_MIPSX_ES3890
_start:
    ld    -16[r29],r4         ; ld and st are fine
    nop
    ldb   -16[r29],r4
    exit  #0
