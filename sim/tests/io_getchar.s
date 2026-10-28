; Reads stdin through the I/O page until -1 (EOF) and echoes it; writes
; one character to stderr through the extension register at 0x14.
; STDIN: ab\n
; STDOUT: ab
; STDERR: !
loop:
_start:
    ld    -65520[r0],r4
    addi  r0,#-1,r5
    beq   r4,r5,done
    nop
    nop
    st    -65536[r0],r4
    b     loop
    nop
    nop
done:
    addi  r0,#33,r4
    st    -65516[r0],r4
    exit  #0
