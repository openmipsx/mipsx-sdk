; args-device.S: the command line for programs run on the device.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; The board hooks that crt0 calls to build main's argc and argv
; (abi §13.3).  Nothing on the device supplies a command line, so argc is
; 0 and argv holds only the null pointer that C requires at argv[argc].

    .text
    .globl  __mipsx_args_size
    .type   __mipsx_args_size,@function
; Returns in r2 the bytes the argv block needs, a multiple of 8.
__mipsx_args_size:
    addi    r0,#8,r2
    ret
    nop
    nop
    .size   __mipsx_args_size,.-__mipsx_args_size

    .globl  __mipsx_args
    .type   __mipsx_args,@function
; Writes the argv block at r4: a single null pointer.  Returns argc (0)
; in r2.
__mipsx_args:
    st      0[r4],r0
    mov     r0,r2
    ret
    nop
    nop
    .size   __mipsx_args,.-__mipsx_args
