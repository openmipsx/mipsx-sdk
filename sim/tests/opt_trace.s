; --trace prints each instruction with its effects, squashed slots
; included.
; ARGS: --trace
; EXIT: 5
; STDERR:          0 00002000: e0080005  addi r0,#5,r4                  ; r4 = 0x00000005
; STDERR: bnesq r0,r0,0x2014             ; not taken, slots squashed
; STDERR: 0000200c: 60000019  nop                            ; squashed
; STDERR: st -65532[r0],r4               ; [0xffff0004] = 0x00000005
_start:
    addi  r0,#5,r4
    bnesq r0,r0,1f
    nop
    nop
    nop
1:  st    -65532[r0],r4
