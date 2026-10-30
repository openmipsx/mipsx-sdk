; Test program for crt0 (rt/tests/test_rt.py): main checks what crt0 set
; up, prints a string from .rodata and returns 42.  A failed check
; returns its own code (10-19) instead.  Plain abi §10 syntax, so that
; llvm-mc can assemble it once it exists.

    .text
    .globl  main
main:
    ; r23, r24 and r28 as abi §13.3 says.
    la      __mipsx_cb0,r8
    lsr     r8,r8,#2
    addi    r0,#10,r2
    bne     r8,cb0,fail
    nop
    nop
    la      __mipsx_cb1,r8
    lsr     r8,r8,#2
    addi    r0,#11,r2
    bne     r8,cb1,fail
    nop
    nop
    la      _gp,r8
    addi    r0,#12,r2
    bne     r8,gp,fail
    nop
    nop
    ; sp is argv: crt0 used no stack beyond the argv block, which is
    ; below __stack_top.
    addi    r0,#13,r2
    bne     r5,sp,fail
    nop
    nop
    la      __stack_top,r8
    bhs     r5,r8,fail
    nop
    nop
    ; argv[argc] is null.
    add     r4,r4,r8
    add     r8,r8,r8
    add     r5,r8,r8
    ld      0[r8],r9
    addi    r0,#14,r2
    bne     r9,r0,fail
    nop
    nop
    ; .data holds its initial values (copied if it runs elsewhere).
    la      answer,r8
    ld      0[r8],r9
    ld      4[r8],r10
    addi    r0,#15,r2
    addi    r0,#41,r11
    bne     r9,r11,fail
    nop
    nop
    li      #0x12345678,r11
    bne     r10,r11,fail
    nop
    nop
    ; .bss is zero (the test may have filled it with junk first).
    la      zeroes,r8
    addi    r0,#64,r9           ; words to check
1:
    ld      0[r8],r10
    addi    r8,#4,r8
    addi    r9,#-1,r9
    addi    r0,#16,r2
    bne     r10,r0,fail
    nop
    nop
    bne     r9,r0,1b
    nop
    nop
    ; The constructor ran, after .bss was cleared.
    la      ctor_ran,r8
    ld      0[r8],r9
    addi    r0,#17,r2
    addi    r0,#1,r11
    bne     r9,r11,fail
    nop
    nop
    ; Print the greeting.
    la      greeting,r8
2:
    ldbu    0[r8],r9
    addi    r8,#1,r8
    beq     r9,r0,3f
    nop
    nop
    stb     -65536[r0],r9       ; putchar
    b       2b
    nop
    nop
3:
    ld      0[r0],r0            ; harmless load: r0 stays zero
    addi    r0,#42,r2
fail:
    ret
    nop
    nop

; A constructor, called through __init_array.
    .globl  ctor
ctor:
    la      ctor_ran,r8
    addi    r0,#1,r9
    st      0[r8],r9
    ret
    nop
    nop

    .section .rodata
greeting:
    .asciz  "hello, crt0\n"

    .section .init_array,"aw"
    .word   ctor

    .data
answer:
    .word   41
    .word   0x12345678

    .bss
    .p2align 2
ctor_ran:
    .space  4
zeroes:
    .space  256
