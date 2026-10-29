; Each hazard report is tagged hardware rule or ABI convention (spec §9:
; vendor code breaks P2 and abi §9.2 on the hardware), and warn mode
; prints totals per rule at exit.
; ARGS: --hazards=warn
; STDERR: load-use hazard (P1): addi r4,#5,r5 reads r4, loaded by the previous instruction at 0x00002004 <_start+0x4> [hardware rule]
; STDERR: load overwrites its own address register r6 (P2): ld 0[r6],r6 [ABI convention]
; STDERR: (abi §9.2): ld -16[r29],r7 [ABI convention]
; STDERR: right after a multiply or divide step [ABI convention]
; STDERR: right after movtos to md [hardware rule]
; STDERR: mipsx-sim: 7 hazard warning(s)
; STDERR: mipsx-sim:   P1: 2 [hardware rule]
; STDERR: mipsx-sim:   P2: 1 [ABI convention]
; STDERR: mipsx-sim:   P3, squashed slot: 1 [ABI convention]
; STDERR: mipsx-sim:   P4: 1 [hardware rule]
; STDERR: mipsx-sim:   P4, after a step: 1 [ABI convention]
; STDERR: mipsx-sim:   §9.2: 1 [ABI convention]
_start:
    st    -16[r29],r0
    ld    -16[r29],r4
    addi  r4,#5,r5            ; P1
    ld    -16[r29],r4
    addi  r4,#5,r5            ; P1
    addi  r29,#-16,r6
    ld    0[r6],r6            ; P2
    nop
    b     1f
    nop
    ld    -16[r29],r7         ; §9.2
1:  bnesq r0,r0,2f
    b     2f                  ; P3 in a squashed slot
    nop
2:  dstep r3,r5,r3
    movfrs md,r8              ; P4 after a step
    movtos r0,md
    mstep r3,r5,r3            ; P4
    exit  #0
