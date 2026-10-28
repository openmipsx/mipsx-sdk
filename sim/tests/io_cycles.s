; Cycle counter: low word latches the high word.  Each instruction or
; squashed slot is one cycle; a memory instruction after a store stalls
; one cycle (P6).
; STDERR-EMPTY
_start:
    ld    -65528[r0],r4       ; cycle counter low
    nop
    ld    -65528[r0],r5       ; 2 cycles later
    ld    -65524[r0],r6       ; high word, latched
    sub   r5,r4,r7
    expect r7,2
    expect r6,0
    ld    -65528[r0],r4
    bnesq r0,r0,0f            ; not taken: 2 squashed slots
    nop
    nop
0:  ld    -65528[r0],r5
    nop
    sub   r5,r4,r7
    expect r7,4               ; ld, beqsq, 2 squashed slots
    ld    -65528[r0],r4
    st    -16[r29],r0
    ld    -65528[r0],r5       ; stalls one cycle after the store
    nop
    sub   r5,r4,r7
    expect r7,3
    ld    -65512[r0],r4       ; instructions retired
    nop
    nop
    ld    -65512[r0],r5
    nop
    sub   r5,r4,r7
    expect r7,3
    exit  #0
