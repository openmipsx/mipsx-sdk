; --variant=store-mem: a memory instruction right after a store is a
; hazard, not just a stall.
; ARGS: --variant=store-mem
; EXIT: 125
; STDERR: memory instruction right after a store (variant store-mem): ld -16[r29],r4
_start:
    st    -16[r29],r0
    ld    -16[r29],r4
    exit  #0
