; args-sim.S: the command line for programs run on mipsx-sim.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; The board hooks that crt0 calls to build main's argc and argv
; (abi §13.3).  The simulator holds the command line and writes the argv
; block through its I/O page (abi §13.5).

    .text
    .globl  __mipsx_args_size
    .type   __mipsx_args_size,@function
; Returns in r2 the bytes the argv block needs, a multiple of 8.
__mipsx_args_size:
    ld      -65500[r0],r2           ; 0xFFFF0024: argv block size
    ret
    nop
    nop
    .size   __mipsx_args_size,.-__mipsx_args_size

    .globl  __mipsx_args
    .type   __mipsx_args,@function
; Writes the argv block at r4 (word aligned, __mipsx_args_size bytes):
; argv[0..argc-1], a null pointer, then the strings.  Returns argc in r2.
__mipsx_args:
    st      -65496[r0],r4           ; 0xFFFF0028: write the block at r4
    ld      -65504[r0],r2           ; 0xFFFF0020: argc
    ret
    nop
    nop
    .size   __mipsx_args,.-__mipsx_args
