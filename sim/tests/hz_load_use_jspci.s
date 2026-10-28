; P1: loaded return address used by jspci (a missing nop before ret).
; EXIT: 125
; STDERR: load-use hazard (P1): ret reads r31
_start:
    la    1f,r4
    lsr   r4,r4,#2
    st    -16[r29],r4
    ld    -16[r29],r31
    ret
    nop
    nop
1:  exit  #0
