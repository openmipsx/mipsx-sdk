; Reserved e_flags bits.
; ELF: flags=0x101
; EXIT: 126
; STDERR: reserved e_flags bits set (0x00000101)
_start:
    exit  #0
