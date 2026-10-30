; shlv counts outside -31..31 are unknown (spec §5), negative ones too.
; EXIT: 125
; STDERR: shlv count -32 is outside -31..31, where spec §5 leaves the result unknown
_start:
    addi  r0,#-32,r5
    addi  r0,#1,r4
    shlv  r4,r5,r6
    exit  #0
