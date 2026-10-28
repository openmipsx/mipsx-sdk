; --stats prints counts at exit, including delay-slot use for S11.
; ARGS: --stats
; STDERR: mipsx-sim: cycles 10, instructions 7, squashed 2, store stalls 1, delay slots 4 (nop 3)
_start:
    st    -16[r29],r0
    ld    -16[r29],r4         ; stalls one cycle after the store
    bnesq r0,r0,1f            ; slots squashed
    nop
    nop
    b     1f
    addi  r0,#1,r5
    nop
1:  st    -65532[r0],r0
