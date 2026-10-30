; The OP 001 variants are competing readings: only one at a time.
; ARGS: --variant=andi-zext --variant=op001-nop
; EXIT: 126
; STDERR: andi-zext, op001-or and op001-nop are alternatives; choose one
_start:
    exit  #0
