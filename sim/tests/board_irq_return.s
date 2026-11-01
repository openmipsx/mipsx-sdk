; SPA3000 board: an interrupt pending when a handler returns.  The
; handler re-arms the timer so that the next interrupt is pending before
; it returns, and does NOT write the interrupt-suppress register.  With
; the spec's rule that no interrupt is taken in a delay slot (processor
; §10), the pending interrupt waits for jpcrs, jpc, jpc and the three
; restarted instructions, and the program counts 5 interrupts and exits
; 0.  variant_irq_in_slot.s runs the same program under
; --variant=irq-in-slot and shows the return sequence being re-entered;
; variant_irq_in_slot_isupp.s adds the suppress store and passes again.
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
