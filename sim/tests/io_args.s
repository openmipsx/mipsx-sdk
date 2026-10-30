; The command line through the I/O page: argc, the argv block's size and
; the block itself, written where the program asks.  mipsx-run appends
; the words of --args after the ELF, whose path is argv[0].
; RUNNER: --args hi --args there
; EXIT: 3
; STDOUT: hi
; STDOUT: there
_start:
    ld    -65500[r0],r4       ; size
    addi  r0,#7,r5
    and   r4,r5,r5
    nop
    bne   r5,r0,bad           ; a multiple of 8
    nop
    nop
    li    #0x100000,r6
    st    -65496[r0],r6       ; write the block at 0x100000
    ld    -65504[r0],r7       ; argc
    addi  r6,#4,r8            ; &argv[1]
next:
    ld    0[r8],r9
    addi  r8,#4,r8
    beq   r9,r0,done          ; argv[argc] is null
    nop
    nop
char:
    ldbu  0[r9],r10
    addi  r9,#1,r9
    beq   r10,r0,eol
    nop
    nop
    st    -65536[r0],r10
    b     char
    nop
    nop
eol:
    addi  r0,#10,r10
    st    -65536[r0],r10
    b     next
    nop
    nop
done:
    st    -65532[r0],r7       ; exit with argc
bad:
    exit  #99
