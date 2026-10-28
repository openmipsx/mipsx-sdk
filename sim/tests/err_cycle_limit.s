; The cycle limit stops an endless loop with status 124.
; ARGS: --max-cycles=1000
; EXIT: 124
; STDERR: cycle limit of 1000 reached at pc
_start:
    b     _start
    nop
    nop
