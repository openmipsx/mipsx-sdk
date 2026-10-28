; P3: a jspci in the second slot of a jspci.
; EXIT: 125
; STDERR: in delay slot 2 of the jspci
_start:
    jmp   1f
    nop
    jmp   1f
    nop
    nop
1:  exit  #0
