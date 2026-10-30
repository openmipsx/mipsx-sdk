; The argv block must be written to a word-aligned address.
; EXIT: 125
; STDERR: argv block address 0x00100002 is not word aligned
_start:
    li    #0x100002,r6
    st    -65496[r0],r6
    exit  #0
