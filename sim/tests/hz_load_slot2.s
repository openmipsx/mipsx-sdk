; abi §9.2: no load in the second delay slot, even when the target does
; not use the register.
; EXIT: 125
; STDERR: load in the second delay slot of the beq at 0x00002000 <_start> (abi §9.2): ld -16[r29],r4
_start:
    b     1f
    nop
    ld    -16[r29],r4
1:  exit  #0
