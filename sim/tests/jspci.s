; jspci: call, return, jump; both delay slots run; the return address is
; the jspci's word address + 3 (spec §6, abi §5.1).
; STDERR-EMPTY
_start:
    addi  r0,#0,r9
callsite:
    call  func                ; jspci r0,#%w(func),r31
    addi  r9,#1,r9            ; slot 1
    addi  r9,#1,r9            ; slot 2
after:
    expect r9,102
    expect r2,%w(after)
    ; jump through a base register with an offset (like cb0/cb1)
    li    %w(target)-100,r23
    jspci r23,#100,r0
    addi  r9,#1,r9
    nop
    exit  #98
target:
    expect r9,103
    ; jspci reads its base before writing the link register
    la    func2,r8
    lsr   r8,r31,#2
    jspci r31,#0,r31
    nop
    nop
back2:
    expect r3,%w(back2)
    exit  #0

func:
    mov   r31,r2
    ret                       ; jspci r31,#0,r0
    addi  r9,#100,r9
    nop
    exit  #97
func2:
    mov   r31,r3
    ret
    nop
    nop
