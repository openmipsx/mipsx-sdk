; With --hazards=warn the hazard is a warning and execution continues
; with sequential semantics.
; ARGS: --hazards=warn
; STDERR: warning: pc 0x00002008 <_start+0x8>: load-use hazard (P1)
; STDERR: mipsx-sim: 1 hazard warning(s)
_start:
    st    -16[r29],r0
    ld    -16[r29],r4
    addi  r4,#5,r5
    expect r5,5
    exit  #0
