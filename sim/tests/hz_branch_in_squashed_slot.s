; P3: the manual allows branches in squashed slots, the ABI does not;
; reported even if squashed.
; EXIT: 125
; STDERR: (P3)
_start:
    bnesq r0,r0,1f
    b     1f
    nop
1:  exit  #0
