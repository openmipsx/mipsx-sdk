; In warn mode, a taken branch in the slot of a taken branch follows the
; pipeline: one instruction runs at the first target, then the second
; target (manual §3.4: the target address is used three fetches later).
; ARGS: --hazards=warn
; STDERR: (P3)
_start:
    addi  r0,#0,r9
    b     first
    b     second
    addi  r9,#1,r9            ; slot 2 of the first branch
    exit  #101
first:
    addi  r9,#10,r9           ; runs once
    addi  r9,#100,r9          ; skipped: the second branch takes effect
    exit  #102
second:
    expect r9,11
    exit  #0
