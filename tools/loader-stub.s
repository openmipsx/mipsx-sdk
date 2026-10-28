; loader-stub.s: the loader at the end of every section mipsx-pack writes.
;
; Copyright 2026 The mipsx-sdk authors.
; SPDX-License-Identifier: Apache-2.0
;
; Written from openmipsx/devices common/firmware-image-format.md and
; docs/abi.md; no vendor code.  mipsx_pack.py holds the assembled words
; (STUB_WORDS) and tools/tests checks that they match this source.  Until
; llvm-mc exists, assemble with:
;     python3 sim/tests/mxasm.py --base 0 tools/loader-stub.s -o stub.elf
;
; The boot selector checks the section and jumps to section data +
; (length - 0x10) (format spec §5, "Order", step 4), in place in flash,
; at an address that depends on which program installed the image
; (format spec §5, flash layout).  So the stub is position-independent:
;
; 1. It finds its own address.  MIPS-X has no PC-relative load or
;    link-and-branch, so it writes a return ('jspci r31,#0,r0' and two
;    nops) to RAM at TRAMP and calls it: the call leaves the word address
;    of 'here' in r31.  The section's last word is its length (as in the
;    stock boot section, format spec §5 Placement), so the packed header
;    is at (end of section) - length.
; 2. It walks the load directory (format spec §4.4):
;      0x01  copy word 3 words from header + word 1 to word 2 (the
;            record as section C's embedded program uses it, §5)
;      0x07  r23 = word 1;  0x05  r24 = word 1
;      0x03  jump to word address (word 1 & 0x3FFFFFFF) with r4 = the
;            packed header's address, as the stock loader does (§4.5)
;    and ignores other record types.  mipsx-pack writes only these.
;    Running off the end of the directory stops in a loop.
;
; It needs no stack and changes only RAM it copies to and TRAMP..TRAMP+11.
; It assumes executing freshly written RAM is safe (no stale instruction
; cache lines); confirm on hardware.

    .set    TRAMP,0x1FF0            ; in the vector area below .text
    .set    JSPCI_RET,0xC7C00000    ; jspci r31,#0,r0
    .set    NOP,0x60000019          ; add r0,r0,r0

stub:
    li      #JSPCI_RET,r2
    li      #NOP,r3
    st      TRAMP[r0],r2
    st      TRAMP+4[r0],r3
    st      TRAMP+8[r0],r3
    jspci   r0,#%w(TRAMP),r31       ; returns to 'here'
    nop
    nop
here:
    lsl     r31,r10,#2              ; byte address of 'here'
    addi    r10,#end-here,r10       ; end of the section
    ld      -4[r10],r11             ; section length (last word)
    nop
    sub     r10,r11,r10             ; r10 = packed header
    ld      4[r10],r12              ; directory offset
    ld      8[r10],r13              ; number of records
    add     r10,r12,r12             ; r12 = first record
next:
    beq     r13,r0,fail             ; no entry record
    nop
    nop
    ld      0[r12],r14              ; type
    ld      4[r12],r15              ; word 1
    ld      8[r12],r16              ; word 2
    ld      12[r12],r17             ; word 3
    addi    r12,#20,r12
    addi    r13,#-1,r13
    addi    r0,#1,r2
    beq     r14,r2,copy
    nop
    nop
    addi    r0,#3,r2
    beq     r14,r2,entry
    nop
    nop
    addi    r0,#7,r2
    bne     r14,r2,1f
    nop
    nop
    mov     r15,r23                 ; 0x07: code base 0
1:
    addi    r0,#5,r2
    bne     r14,r2,next
    nop
    nop
    b       next
    mov     r15,r24                 ; 0x05: code base 1 (delay slot)
    nop
copy:                               ; r15 offset, r16 address, r17 words
    add     r10,r15,r15
    beq     r17,r0,next
    nop
    nop
2:
    ld      0[r15],r2
    addi    r15,#4,r15
    addi    r17,#-1,r17
    st      0[r16],r2
    addi    r16,#4,r16
    bne     r17,r0,2b
    nop
    nop
    b       next
    nop
    nop
entry:
    lsl     r15,r15,#2              ; drop bits 31-30 (bit 30 is a flag)
    lsr     r15,r15,#2
    mov     r10,r4                  ; r4 = packed header
    jspci   r15,#0,r0
    nop
    nop
fail:
    b       fail
    nop
    nop

; The last four words of the section.  The boot selector enters at
; length - 0x10, the branch below.
    b       stub
    nop
    nop
    .word   0                       ; section length, filled in by mipsx-pack
end:
