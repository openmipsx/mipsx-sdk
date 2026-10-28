; ...unless RAM is made bigger.
; BASE: 0x300000
; ARGS: --mem-size=0x400000
; EXIT: 7
_start:
    li    0x3FFFFC,r4
    st    0[r4],r4            ; last word of RAM
    exit  #7
