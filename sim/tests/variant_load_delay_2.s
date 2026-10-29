; --variant=load-delay-2: P1 also applies to the second instruction
; after a load.
; ARGS: --variant=load-delay-2
; EXIT: 125
; STDERR: error: pc 0x0000200c <_start+0xc>: load-use hazard at distance 2 (variant load-delay-2): mov r4,r5 reads r4, loaded at 0x00002004 <_start+0x4>
_start:
    nop
    ld    -16[r29],r4
    nop
    add   r4,r0,r5
    exit  #0
