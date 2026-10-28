; P1 inside delay slots: a load in slot 1 used by slot 2.
; EXIT: 125
; STDERR: load-use hazard (P1): mov r4,r5 reads r4
_start:
    b     1f
    ld    -16[r29],r4
    mov   r4,r5
1:  exit  #0
