; SPA3000 board: the RTL8019AS window (peripherals.md §8) is not modelled
; yet, and says so.
; ARGS: --board=spa3000
; EXIT: 125
; STDERR: load from RTL8019AS register 1 at 0x14000070: the Ethernet controller is not modelled yet
_start:
    li    0x14000070,r4
    ldbu  0[r4],r5
    exit  #0
