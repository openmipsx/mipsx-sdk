; Little-endian ELF files are rejected (abi §11.1).
; ELF: data=1
; EXIT: 126
; STDERR: not a big-endian ELF file
_start:
    exit  #0
