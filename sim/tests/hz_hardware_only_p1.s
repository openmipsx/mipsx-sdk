; --hazard-rules=hardware still reports hardware rules: one load delay
; slot (spec §9).
; ARGS: --hazard-rules=hardware
; EXIT: 125
; STDERR: load-use hazard (P1): addi r4,#5,r5 reads r4
; STDERR: [hardware rule]
_start:
    st    -16[r29],r0
    ld    -16[r29],r4
    addi  r4,#5,r5
    exit  #0
