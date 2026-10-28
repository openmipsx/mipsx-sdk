; P3: trap in a delay slot.
; EXIT: 125
; STDERR: trap #3 in delay slot 1 of the beq
_start:
    b     1f
    trap  #3
    nop
1:  exit  #0
