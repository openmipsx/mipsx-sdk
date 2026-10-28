; P3: a branch in a delay slot.
; EXIT: 125
; STDERR: error: pc 0x00002004 <_start+0x4>: b 0x2014 in delay slot 1 of the beq at 0x00002000 <_start> (P3)
_start:
    b     1f
    b     1f
    nop
    nop
    nop
1:  exit  #0
