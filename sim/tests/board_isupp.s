; SPA3000 board: the interrupt-suppress register at 0x20004028
; (peripherals.md §4, Hypothesis, strong).  Writing S holds interrupts
; off for the next 15 - S instructions: 0 gives 15, 0xE gives 1, 0xF
; none.  Each round leaves a timer interrupt pending while PSW M is set,
; writes 0 (15 instructions, as the firmware does before its PSW
; read-modify-write), clears M, re-arms with S, and runs a nop and then
; a row of addis; the handler records the head of the PC chain, which
; must be the first instruction after the 15 - S held off by the re-arm.
; BASE: 0x0
; ARGS: --board=spa3000
; EXIT: 0

vector:
    nop
    jmp   irq
    nop
    nop

_start:
    li    0x20000000,r27
    li    2,r1
    st    0x4034[r27],r1     ; enable source 1 (the timer)
    movfrs psw,r2
    andi  r2,#-17,r2         ; r2 = PSW with bit 4 (M) clear
    addi  r2,#0x10,r3        ; r3 = PSW with M set (bit 4 is clear in r2)

    ; S = 0: 15 held off, the nop and 14 addis.
    li    -1,r1
    st    0x400C[r27],r1     ; the count passes to 0 next cycle: pending
    mov   r0,r20
    st    0x4028[r27],r0     ; hold 15 while M is cleared
    movtos r2,psw
    li    0,r1
    st    0x4028[r27],r1     ; re-arm with S
    nop
run0:
    .rept 20
    addi  r5,#1,r5
    .endr
    movtos r3,psw
    expect r20,%w(run0)+14

    ; S = 9: 6 held off, the nop and 5 addis.
    li    -1,r1
    st    0x400C[r27],r1     ; the count passes to 0 next cycle: pending
    mov   r0,r20
    st    0x4028[r27],r0     ; hold 15 while M is cleared
    movtos r2,psw
    li    9,r1
    st    0x4028[r27],r1     ; re-arm with S
    nop
run9:
    .rept 20
    addi  r5,#1,r5
    .endr
    movtos r3,psw
    expect r20,%w(run9)+5

    ; S = 0xE: 1 held off, the nop.
    li    -1,r1
    st    0x400C[r27],r1     ; the count passes to 0 next cycle: pending
    mov   r0,r20
    st    0x4028[r27],r0     ; hold 15 while M is cleared
    movtos r2,psw
    li    0xE,r1
    st    0x4028[r27],r1     ; re-arm with S
    nop
runE:
    .rept 20
    addi  r5,#1,r5
    .endr
    movtos r3,psw
    expect r20,%w(runE)

    ; S = 0xF: none held off; the interrupt is taken at the nop, the instruction before the row.
    li    -1,r1
    st    0x400C[r27],r1     ; the count passes to 0 next cycle: pending
    mov   r0,r20
    st    0x4028[r27],r0     ; hold 15 while M is cleared
    movtos r2,psw
    li    0xF,r1
    st    0x4028[r27],r1     ; re-arm with S
    nop
runF:
    .rept 20
    addi  r5,#1,r5
    .endr
    movtos r3,psw
    expect r20,%w(runF)-1

    ; The upper bits are ignored: 0xFFFFFFF0 is S = 0.
    li    -1,r1
    st    0x400C[r27],r1     ; the count passes to 0 next cycle: pending
    mov   r0,r20
    st    0x4028[r27],r0     ; hold 15 while M is cleared
    movtos r2,psw
    li    0xFFFFFFF0,r1
    st    0x4028[r27],r1     ; re-arm with S
    nop
runU:
    .rept 20
    addi  r5,#1,r5
    .endr
    movtos r3,psw
    expect r20,%w(runU)+14

    ; The register reads back as written (modelling choice); the handler
    ; left 0 there.
    ld    0x4028[r27],r6
    nop
    expect r6,0
    li    0x12345678,r1
    st    0x4028[r27],r1
    ld    0x4028[r27],r6
    nop
    expect r6,0x12345678
    expect r5,100
    exit  #0

; Handler: record the head PC (as a word address) in r20, acknowledge,
; and return as the spec says every handler must: the last store before
; jpcrs writes 0 to 0x4028 (§4; processor-es3890.md §10).
irq:
    movfrs pcm4,r20
    movfrs pcm4,r21
    movfrs pcm4,r22
    st    0x4010[r27],r0
    movtos r20,pcm1
    movtos r21,pcm1
    movtos r22,pcm1
    st    0x4028[r27],r0
    jpcrs
    jpc
    jpc
