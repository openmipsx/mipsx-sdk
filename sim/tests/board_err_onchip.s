; SPA3000 board: on-chip registers outside the timer block are not
; modelled yet (peripherals.md §2).  Without --board the address is
; unmapped, as before.
; ARGS: --board=spa3000
; EXIT: 125
; STDERR: store to on-chip register 0x20008100, which is not modelled yet
_start:
    li    0x20000000,r4
    li    0x384,r5
    st    0x8100[r4],r5
    exit  #0
