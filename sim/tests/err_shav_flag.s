; shav needs EF_MIPSX_VSHIFT under every variant, including rotlcb.
; ARGS: --variant=rotlcb
; ELF: flags=1
; EXIT: 125
; STDERR: shav is an ES3890 variable shift, but the program's e_flags lack EF_MIPSX_VSHIFT
_start:
    shav  r4,r5,r6
    exit  #0
