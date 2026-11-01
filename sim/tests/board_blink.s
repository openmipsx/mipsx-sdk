; SPA3000 board: the LED milestone on the simulator.  Sets up the 10 ms
; timer tick (peripherals.md §4), takes the timer interrupt at word 0
; (processor-es3890.md §10), kicks the watchdog every second (§5) and
; toggles the status LEDs on port 0 bit 3 every 50 ticks (§6), as the
; stock firmware does.  Runs for 3 s of board time (300 ticks), so the
; LED log must show toggles 0.5 s = 50 x 809,930 cycles apart, and the
; 1.5 s watchdog must not bite.  Each tick is a few cycles longer than
; 809,930: the handler writes back count - 809,930 some cycles after it
; read the count, and the counter runs on meanwhile (§4 gives the
; period without that gap).  1,000 cycles is 12 us.
; BASE: 0x0
; ARGS: --board=spa3000 --watchdog=1.5
; STDERR: watchdog enabled (timeout 1.500 s)
; STDERR: port0 led off
; STDERR: port0 led on
; NOT-STDERR: watchdog reset
; LOG-PERIOD: port0 led 40496500 1000
; EXIT: 0

; Interrupt vector (word 0): a no-op, a jump to the handler, two slots.
vector:
    nop
    jmp   irq
    nop
    nop

_start:
    li    0x20000000,r27     ; on-chip registers
    li    0x14000003,r26     ; system-control register file
    ; Kick the watchdog (0x402C bit 2 low then high), then enable it
    ; (reg 3 bit 7), in that order (§5).
    li    0x32,r1
    st    0x402C[r27],r1
    li    0x36,r1
    st    0x402C[r27],r1
    li    0x06,r1            ; address byte: reg 3, write
    stb   0[r26],r1
    li    0xBC,r1
    stb   0[r26],r1
    ; Port 0 bit 3 driven high = LEDs off: data first, then direction (§6).
    li    0x08,r24           ; LED data shadow
    li    0x08,r1            ; reg 4 (data), write
    stb   0[r26],r1
    stb   0[r26],r24
    li    0x0A,r1            ; reg 5 (direction), write
    stb   0[r26],r1
    stb   0[r26],r24
    ; Timer: acknowledge, load -810,000, enable source 1, unmask (§4, §7.3).
    mov   r0,r23             ; tick count
    mov   r0,r18             ; ticks since the last LED toggle
    mov   r0,r17             ; ticks since the last kick
    st    0x4010[r27],r0
    li    -810000,r1
    st    0x400C[r27],r1
    li    2,r1
    st    0x4034[r27],r1
    movfrs psw,r1
    andi  r1,#-17,r1         ; clear PSW bit 4, the interrupt mask
    movtos r1,psw
    li    300,r4
loop:
    bge   r23,r4,done
    nop
    nop
    b     loop
    nop
    nop
done:
    exit  #0

; Timer tick.  Uses only registers the main program never touches, so
; nothing but the PC chain needs saving.
irq:
    movfrs pcm4,r20          ; the three PCs to restart (§10)
    movfrs pcm4,r21
    movfrs pcm4,r22
    st    0x4010[r27],r0     ; acknowledge
    ld    0x400C[r27],r25    ; keep the overshoot: count -= 809,930
    li    809930,r19
    sub   r25,r19,r25
    st    0x400C[r27],r25
    addi  r23,#1,r23
    addi  r18,#1,r18
    li    50,r19
    bne   r18,r19,noled
    nop
    nop
    mov   r0,r18
    li    0x08,r19
    xor   r24,r19,r24        ; toggle the LED latch
    li    0x08,r1            ; reg 4, write
    stb   0[r26],r1
    stb   0[r26],r24
noled:
    addi  r17,#1,r17
    li    100,r19
    bne   r17,r19,nokick
    nop
    nop
    mov   r0,r17
    li    0x32,r1            ; kick
    st    0x402C[r27],r1
    li    0x36,r1
    st    0x402C[r27],r1
nokick:
    ; A store at the head of the chain has already been done (§10):
    ; restart the no-op at word 0 in its place.
    lsl   r20,r19,#2
    ld    0[r19],r16
    nop
    lsr   r16,r16,#27        ; opcode and sub-opcode bits
    li    0x12,r1            ; st
    beq   r16,r1,headstore
    nop
    nop
    li    0x13,r1            ; stb
    beq   r16,r1,headstore
    nop
    nop
    li    0x16,r1            ; sth
    bne   r16,r1,restore
    nop
    nop
headstore:
    mov   r0,r20
restore:
    movtos r20,pcm1
    movtos r21,pcm1
    movtos r22,pcm1
    ; The last store of every handler before jpcrs writes 0 to the
    ; interrupt-suppress register (peripherals.md §4; processor §10), so
    ; that a pending interrupt cannot split the return sequence.
    st    0x4028[r27],r0
    jpcrs
    jpc
    jpc
