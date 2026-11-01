; SPA3000 board: a system-control data byte needs an address byte first
; (peripherals.md §3).
; ARGS: --board=spa3000
; EXIT: 125
; STDERR: system-control data byte read without an address byte first
_start:
    li    0x14000003,r4
    ldbu  0[r4],r5
    exit  #0
