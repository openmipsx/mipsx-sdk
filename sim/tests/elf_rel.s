; Relocatable objects are rejected.
; ELF: etype=1
; EXIT: 126
; STDERR: not an executable
_start:
    exit  #0
