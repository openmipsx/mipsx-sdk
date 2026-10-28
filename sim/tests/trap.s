; trap: enters vector * 8 (word address) with the PC chain frozen and
; PSWcurrent copied to PSWother; the instruction after the trap does not
; run before the handler.  The handler saves the chain with movfrs pcm4
; and returns with movtos pcm1 and jpcrs/jpc/jpc (manual App. VI, Figure
; VI-2), which restarts the instruction after the trap.  The jpc in the
; slots of jpcrs/jpc is not a P3 violation.
; BASE: 0
; STDERR-EMPTY
    nop                       ; address 0 must hold a nop (manual App. I)
    .org  0x100               ; vector 8 = word 64 = byte 0x100
handler:
    movfrs pcm4,r20           ; instruction before the trap
    movfrs pcm4,r21           ; the trap
    movfrs pcm4,r22           ; instruction after the trap: restart here
    movfrs psw,r11
    addi  r13,#1,r13          ; count handler entries
    movtos r0,pcm1            ; nop at 0
    movtos r0,pcm1            ; nop at 0
    movtos r22,pcm1
    jpcrs
    jpc
    jpc

    .org  0x200
_start:
    addi  r0,#0,r9
    movfrs psw,r10
before:
    addi  r0,#0,r13
trap_at:
    trap  #8
after:
    addi  r9,#1,r9            ; restarted after the handler
    addi  r9,#10,r9
    movfrs psw,r12
    expect r9,11
    expect r13,1
    expect r20,%w(before)
    expect r21,%w(trap_at)
    expect r22,%w(after)
    expect r10,0x155          ; reset: S I M V e
    expect r11,0x1FE          ; S off, other bits = copy of current bits
    expect r12,0x1FF          ; PSWcurrent restored, shifting on
    exit  #0
