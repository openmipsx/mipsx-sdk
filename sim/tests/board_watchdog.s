; SPA3000 board: the watchdog bites when it is enabled (system-control
; reg 3 bit 7, peripherals.md §5) and not kicked, and the simulator
; stops with status 123.  A 1 ms timeout is 81,000 cycles.
; ARGS: --board=spa3000 --watchdog=0.001
; EXIT: 123
; STDERR: watchdog enabled (timeout 0.001 s)
; STDERR: watchdog reset at pc
; STDERR: no kick for 0.001 s
_start:
    li    0x20000000,r27
    li    0x14000003,r26
    li    0x32,r1            ; one kick first
    st    0x402C[r27],r1
    li    0x36,r1
    st    0x402C[r27],r1
    li    0x06,r1            ; reg 3, write
    stb   0[r26],r1
    li    0xBC,r1
    stb   0[r26],r1
spin:
    b     spin
    nop
    nop
