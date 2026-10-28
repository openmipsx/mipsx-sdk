; The §9.2 rule is static: a load in the second slot of a squashing
; branch is reported even when the slots are squashed.
; EXIT: 125
; STDERR: load in the second delay slot of the bne
_start:
    bnesq r0,r0,1f
    nop
    ld    -16[r29],r4
1:  exit  #0
