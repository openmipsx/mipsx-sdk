; exit-sim.S: exit and _exit for programs run on mipsx-sim.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Stores the status (r4) to the simulator's exit register in the I/O page
; (abi §13.5); the simulator stops with the low 8 bits as its exit
; status.  'exit' is weak so that a C library's exit (which runs atexit
; handlers and then calls _exit) replaces it.

    .text
    .weak   exit
    .type   exit,@function
exit:
    .globl  _exit
    .type   _exit,@function
_exit:
    st      -65532[r0],r4           ; 0xFFFF0004: exit register
1:
    b       1b                      ; not reached
    nop
    nop
    .size   _exit,.-_exit
