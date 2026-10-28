; EF_MIPSX_VSHIFT is reserved until the encoding is known.
; ELF: flags=3
; EXIT: 126
; STDERR: EF_MIPSX_VSHIFT is set
_start:
    exit  #0
