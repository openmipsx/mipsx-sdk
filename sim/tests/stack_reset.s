; Without crt0, sp starts 16 bytes below the top of RAM, 8-byte aligned,
; and the other registers are zero.
; STDERR-EMPTY
_start:
    expect r29,0x1FFFF0
    expect r31,0
    expect r4,0
    st    0[r29],r29          ; usable
    st    12[r29],r29         ; last word of RAM
    exit  #0
