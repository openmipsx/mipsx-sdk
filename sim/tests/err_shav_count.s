; shav counts outside -31..31 are unknown (spec §5): the simulator stops
; rather than guess.
; EXIT: 125
; STDERR: shav count 32 is outside -31..31, where spec §5 leaves the result unknown
_start:
    addi  r0,#31,r5
    addi  r0,#1,r4
    shav  r4,r5,r6            ; 31 is fine
    addi  r0,#32,r5
    shav  r4,r5,r6
    exit  #0
