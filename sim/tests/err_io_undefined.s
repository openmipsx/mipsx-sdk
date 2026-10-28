; Undefined I/O page registers.
; EXIT: 125
; STDERR: store to undefined I/O page address 0xffff0080
_start:
    st    -65408[r0],r0
    exit  #0
