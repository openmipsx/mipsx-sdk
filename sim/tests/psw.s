; movtos/movfrs psw: writable in system state except e and E; a no-op in
; user state; a trap returns to system state (manual §2.4, §2.5).
; BASE: 0
; STDERR-EMPTY
    nop
    .org  0x20                ; vector 1
    movfrs psw,r11
    movfrs pcm4,r0
    movfrs pcm4,r0
    movfrs pcm4,r22
    expect r11,0x400001FE     ; system state; u = previous U
    expect r22,%w(after)
    exit  #0
    .org  0x200
_start:
    movfrs psw,r4
    expect r4,0x155
    li    0x0000FE40,r5       ; tries to set E bits and clear e
    movtos r5,psw
    movfrs psw,r6
    expect r6,0x0000E140      ; e and E kept as they were
    li    0x80000155,r5       ; enter user state
    movtos r5,psw
    movfrs psw,r6
    expect r6,0x80000155
    movtos r0,psw             ; ignored in user state
    movfrs psw,r6
    expect r6,0x80000155
    trap  #1
after:
    exit  #1                  ; not reached: the handler exits
