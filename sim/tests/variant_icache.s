; --variant=icache: fetching a word that was stored to since the program
; was loaded is a hazard.
; ARGS: --variant=icache
; EXIT: 125
; STDERR: fetch of a word stored to since the program was loaded (variant icache)
_start:
    la    patch,r4
    li    0x60000019,r5
    st    0[r4],r5
    nop
patch:
    exit  #1
    exit  #0
