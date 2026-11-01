; SPA3000 board, --variant=irq-in-slot: the program of board_irq_return.s
; (a handler that leaves the next interrupt pending when it returns and
; does not write the interrupt-suppress register).  When the simulator
; may take an interrupt in a delay slot, the pending one is taken in the
; first slot of jpcrs, after it has restored the PSW, and the handler
; re-enters with its own jpc at the head of the chain: a return
; sequence that cannot be restarted.  The handler detects that and exits
; 7.  So on a chip that takes interrupts in delay slots, the suppress
; store is what protects the return (processor §10); the spec cannot
; tell the two readings apart from the stock firmware, which always
; writes it.
; BASE: 0x0
; ARGS: --board=spa3000 --variant=irq-in-slot
; EXIT: 7

vector:
    nop
    jmp   irq
    nop
    nop

_start:
    li    0x20000000,r27
    li    2,r1
    st    0x4034[r27],r1     ; enable the timer source
    li    -1,r1
    st    0x400C[r27],r1     ; pending next cycle
    mov   r0,r23
    movfrs psw,r2
    andi  r2,#-17,r2
    movtos r2,psw            ; unmask
    li    5,r4
loop:
    bge   r23,r4,done
    nop
    nop
    b     loop
    nop
    nop
done:
    exit  #0

; Handler: count in r23; if the head of the chain is one of the return
; sequence's own instructions, the sequence was re-entered: exit 7.
irq:
    movfrs pcm4,r20
    movfrs pcm4,r21
    movfrs pcm4,r22
    st    0x4010[r27],r0     ; acknowledge
    li    %w(ret1),r1
    beq   r20,r1,reentered
    nop
    nop
    li    %w(ret2),r1
    beq   r20,r1,reentered
    nop
    nop
    addi  r23,#1,r23
    li    5,r1
    beq   r23,r1,last
    nop
    nop
    li    -1,r1
    st    0x400C[r27],r1     ; the next interrupt is pending before we return
last:
    movtos r20,pcm1
    movtos r21,pcm1
    movtos r22,pcm1
    jpcrs
ret1:
    jpc
ret2:
    jpc
reentered:
    exit  #7
