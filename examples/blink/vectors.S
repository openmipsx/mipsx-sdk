; vectors.S: the exception entry at address 0 for the blink example.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; processor-es3890.md §10: interrupts enter at word address 0, and the
; stock firmware keeps a no-op there followed by a jump and its two
; slots.  This program never enables an interrupt, but an exception
; (alignment, §3) might arrive here.  It stops in a loop without
; kicking the watchdog: with the watchdog enabled the unit resets; with
; it off the unit hangs, and the dead-man net of bootrec.c makes the
; next reset start the recovery program if the hang came before the
; restore.  The loop is in .text; only the four words below sit at 0.
;
; The section is marked writable and not executable on purpose: lld
; puts sections with the same flags into one PT_LOAD, and with "ax" the
; vectors and .text would become a single segment from 0 to the end of
; .text, with 8 KB of padding stored in the image and a r23 value that
; the verifier's §4.4 rule rejects.  With "aw" the four words are their
; own segment at 0.  The flags mean nothing on this hardware.

    .section .vectors,"aw",@progbits
    .globl  __vectors
__vectors:
    nop
    b       __exception_stop
    nop
    nop

    .text
    .globl  __exception_stop
    .type   __exception_stop,@function
__exception_stop:
1:
    b       1b
    nop
    nop
    .size   __exception_stop,.-__exception_stop
