; --hazard-rules=hardware leaves out the ABI conventions, which vendor
; code breaks on the hardware (spec §9): a load into its own address
; register gives the loaded value, and a load may sit in the second
; delay slot.
; ARGS: --hazard-rules=hardware
; STDERR-EMPTY
_start:
    la    word,r4
    nop
    ld    0[r4],r4            ; P2
    nop
    expect r4,0x1234
    b     1f
    nop
    ld    -16[r29],r7         ; §9.2
1:  bnesq r0,r0,2f
    b     2f                  ; P3 in a squashed slot
    nop
2:  dstep r3,r5,r3
    movfrs md,r8              ; P4 after a step
    exit  #0
word:
    .word 0x1234
