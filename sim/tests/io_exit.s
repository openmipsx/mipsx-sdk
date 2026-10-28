; The exit register: the simulator's status is the low 8 bits.
; EXIT: 42
; STDERR-EMPTY
_start:
    addi  r0,#42,r4
    st    -65532[r0],r4
    exit  #1                  ; not reached
