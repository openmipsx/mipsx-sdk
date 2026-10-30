; crt0.S: start-up code for MIPS-X (ES3890) programs.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Implements the start-up contract of docs/abi.md §13.3, in the assembler
; syntax of abi §10.  The linker script (rt/sim.ld or rt/device.ld)
; defines every symbol used here (abi §13.1).  It needs no preprocessing:
; the file is .S only by convention, so that Clang's driver accepts it.
;
; _start is entered with the stack pointer and the code base registers in
; any state.  It does not return.  main is called with argc and argv
; from the board's hooks in rt/args-sim.S (simulator: the command line,
; through the I/O page) or rt/args-device.S (device: none); the argv
; block sits at the top of the stack, above main's frame.  main's result
; is passed to exit, which rt/exit-sim.S (simulator: the I/O page exit
; register) or rt/exit-device.S (device: stop) provides.
;
; Every branch and jump below has its two delay slots written out, and no
; loaded register is read by the next instruction (abi §9).

    .section .text.start,"ax",@progbits
    .globl  _start
    .type   _start,@function
_start:
    ; 1. Stack pointer.
    la      __stack_top,sp
    ; 2. Code base registers (word addresses) and the global pointer.
    ;    'la' uses %hi/%lo only, which do not depend on these registers.
    la      __mipsx_cb0,cb0
    lsr     cb0,cb0,#2
    la      __mipsx_cb1,cb1
    lsr     cb1,cb1,#2
    la      _gp,gp
    ; 3. Overflow traps: abi §13.3 relies on the boot environment having
    ;    masked them, until the ES3890's PSW layout is confirmed (abi §2.3).

    ; 4a. Copy .data and .sdata from their load address, if it differs.
    la      __data_load,r4
    la      __data_start,r5
    la      __data_end,r6
    beq     r4,r5,.Lcopied          ; already in place
    nop
    nop
    bhs     r5,r6,.Lcopied          ; empty
    nop
    nop
.Lcopy:
    ld      0[r4],r7
    addi    r4,#4,r4
    st      0[r5],r7
    addi    r5,#4,r5
    blo     r5,r6,.Lcopy
    nop
    nop
.Lcopied:
    ; 4b. Clear .sbss and .bss (word aligned by the linker script).
    la      __bss_start,r5
    la      __bss_end,r6
    bhs     r5,r6,.Lcleared
    nop
    nop
.Lclear:
    st      0[r5],r0
    addi    r5,#4,r5
    blo     r5,r6,.Lclear
    nop
    nop
.Lcleared:
    ; 4c. Run the constructors in __init_array.  Entries are function
    ;     pointers, so byte addresses (abi §4): shift before jspci.
    ;     r16 and r17 are callee-saved, so they survive the calls.
    la      __init_array_start,r16
    la      __init_array_end,r17
    bhs     r16,r17,.Linit_done
    nop
    nop
.Linit:
    ld      0[r16],r2
    addi    r16,#4,r16
    lsr     r2,r2,#2
    jspci   r2,#0,r31
    nop
    nop
    blo     r16,r17,.Linit
    nop
    nop
.Linit_done:
    ; 5. exit(main(argc, argv)).  Make room for the argv block at the
    ;    top of the stack (the size keeps sp 8-aligned), have the board
    ;    fill it in, and pass its address as argv.
    call    __mipsx_args_size
    nop
    nop
    sub     sp,r2,sp
    mov     sp,r4
    call    __mipsx_args
    nop
    nop
    mov     r2,r4
    mov     sp,r5
    call    main
    nop
    nop
    mov     r2,r4
    call    exit
    nop
    nop
.Lhang:                             ; exit does not return
    b       .Lhang
    nop
    nop
    .size   _start,.-_start
