; SPA3000 board: address decode and register behaviour (peripherals.md
; §1, §3, §4, §6; flash.md §1).
; ARGS: --board=spa3000
; STDERR: port0 eth-reset asserted
; STDERR: port0 si3210-reset released
; NOT-STDERR: port0 led
; STDERR: flash sector 0x00000 erased
_start:
    li    0x20000000,r27
    li    0x14000003,r26

    ; DRAM aliases at 0x02000000 and 0x12000000 (§1).
    li    0x12000100,r4
    li    0xDEADBEEF,r5
    st    0[r4],r5
    ld    0x100[r0],r6
    li    0x02000100,r4
    ld    0[r4],r7
    expect r6,0xDEADBEEF
    expect r7,0xDEADBEEF

    ; System control (§3): straps read 1 on this board; address bits 1-0
    ; are not decoded; registers read back as written.
    li    0x03,r1            ; reg 1, read
    stb   0[r26],r1
    ldbu  0[r26],r4
    li    0x05,r1            ; reg 2, read, through 0x14000000
    stb   -3[r26],r1
    ldbu  -3[r26],r5
    expect r4,0x10
    expect r5,0x01
    li    0x02,r1            ; reg 1, write 0x31 (the read value OR 0x21)
    stb   0[r26],r1
    li    0x31,r1
    stb   0[r26],r1
    li    0x03,r1
    stb   0[r26],r1
    ldbu  0[r26],r4
    expect r4,0x31
    li    0x2B,r1            ; reg 0x15, read: unwritten, 0
    stb   0[r26],r1
    ldbu  0[r26],r4
    expect r4,0

    ; Port 0 (§6): data 0x67 then direction 0x67, the firmware's first
    ; write; bit 3 (LED) stays released, as from reset, so it is not
    ; logged.
    li    0x08,r1
    stb   0[r26],r1
    li    0x67,r1
    stb   0[r26],r1
    li    0x0A,r1
    stb   0[r26],r1
    li    0x67,r1
    stb   0[r26],r1

    ; Flash (flash.md §1): erased without an image; autoselect ID through
    ; both windows; program clears bits; sector erase.
    li    0x1C000000,r8
    li    0x0C000000,r9
    ldbu  0[r8],r4
    ld    0x1000[r9],r5
    expect r4,0xFF
    expect r5,0xFFFFFFFF
    li    0xAA,r1
    stb   0x5555[r8],r1      ; only A10-A0 are decoded
    li    0x55,r1
    stb   0x2AAA[r8],r1
    li    0x90,r1
    stb   0x555[r8],r1
    ldbu  0[r8],r4
    ldbu  1[r8],r5
    li    0x0C100001,r10     ; 1 MB repeats through the window
    ldbu  0[r10],r6
    ldbu  2[r8],r7
    expect r4,0x01
    expect r5,0x38
    expect r6,0x38
    expect r7,0x00
    li    0xF0,r1            ; reset to read array
    stb   0[r8],r1
    ldbu  0[r8],r4
    expect r4,0xFF
    li    0xAA,r1
    stb   0x555[r8],r1
    li    0x55,r1
    stb   0x2AA[r8],r1
    li    0xA0,r1
    stb   0x555[r8],r1
    li    0x5A,r1
    stb   0x1234[r8],r1
    ldbu  0x1234[r9],r4
    ld    0x1234[r8],r5
    expect r4,0x5A
    expect r5,0x5AFFFFFF
    li    0xAA,r1            ; programming can only clear bits
    stb   0x555[r8],r1
    li    0x55,r1
    stb   0x2AA[r8],r1
    li    0xA0,r1
    stb   0x555[r8],r1
    li    0xA5,r1
    stb   0x1234[r8],r1
    ldbu  0x1234[r8],r4
    expect r4,0x00
    li    0xAA,r1            ; sector erase
    stb   0x555[r8],r1
    li    0x55,r1
    stb   0x2AA[r8],r1
    li    0x80,r1
    stb   0x555[r8],r1
    li    0xAA,r1
    stb   0x555[r8],r1
    li    0x55,r1
    stb   0x2AA[r8],r1
    li    0x30,r1
    stb   0x1234[r8],r1
    ldbu  0x1234[r8],r4
    expect r4,0xFF

    ; Nothing answers at 0x18000000 (§1).
    li    0x18000000,r4
    ld    0[r4],r5
    expect r5,0

    ; Timer (§4): counts up one per cycle; the load lands one cycle after
    ; the store (the P6 stall).
    li    100,r1
    st    0x400C[r27],r1
    ld    0x400C[r27],r4
    nop
    expect r4,101
    ; The interrupt source sets status bit 1 when the count passes from
    ; negative to zero, with the source disabled nothing is pending; the
    ; acknowledge clears it.
    st    0x4034[r27],r0
    li    -4,r1
    st    0x400C[r27],r1
    nop
    nop
    nop
    nop
    nop
    ld    0x4038[r27],r4
    ld    0x4034[r27],r5
    expect r4,2
    expect r5,0
    st    0x4010[r27],r0
    ld    0x4038[r27],r4
    nop
    expect r4,0
    ; GPIO and latches read back (§2).
    li    0x36,r1
    st    0x402C[r27],r1
    li    0x1BDF3E,r1
    st    0x4004[r27],r1
    ld    0x402C[r27],r4
    ld    0x4004[r27],r5
    expect r4,0x36
    expect r5,0x1BDF3E
    exit  #0
