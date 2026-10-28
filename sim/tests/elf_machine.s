; Wrong e_machine.
; ELF: machine=8
; EXIT: 126
; STDERR: e_machine is 8, not EM_MIPS_X (51)
_start:
    exit  #0
