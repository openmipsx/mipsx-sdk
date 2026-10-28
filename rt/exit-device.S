; exit-device.S: exit and _exit for programs on the device.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; There is no host to return to, and how to reset the ES3890 is not yet
; known, so the program stops here in a loop (with the status in r4, for
; a debugger).  A later version may reset the unit instead.  'exit' is
; weak so that a C library's exit replaces it.

    .text
    .weak   exit
    .type   exit,@function
exit:
    .globl  _exit
    .type   _exit,@function
_exit:
1:
    b       1b
    nop
    nop
    .size   _exit,.-_exit
