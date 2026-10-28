; The cycle counter must be read with a word load.
; EXIT: 125
; STDERR: must be read with a word load
_start:
    ldhu  -65528[r0],r4
    exit  #0
