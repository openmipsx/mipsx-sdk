; Prints through the I/O page putchar register and exits with 0.
; STDOUT: Hi
; STDERR-EMPTY
_start:
    addi r0,#72,r4
    st   -65536[r0],r4      ; putchar 'H'
    addi r0,#105,r4
    stb  -65536[r0],r4      ; any width
    addi r0,#10,r4
    sth  -65536[r0],r4
    st   -65532[r0],r0      ; exit(0)
