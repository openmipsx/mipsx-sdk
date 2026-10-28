; --disassemble: every instruction form, encoded by the test assembler
; from the spec and decoded by the simulator; the printed syntax is
; abi §10 with the aliases of §10.5.
; ARGS: --disassemble
; STDOUT: _start:
; STDOUT: 00002000: 810a0004  ld 4[r4],r5
; STDOUT: 00002004: 910bfffc  st -4[r4],r5
; STDOUT: 00002008: a10a0001  ldbu 1[r4],r5
; STDOUT: 0000200c: a90a0001  ldb 1[r4],r5
; STDOUT: 00002010: 890a0002  ldhu 2[r4],r5
; STDOUT: 00002014: b90a0002  ldh 2[r4],r5
; STDOUT: 00002018: 990a0003  stb 3[r4],r5
; STDOUT: 0000201c: b10a0002  sth 2[r4],r5
; STDOUT: 00002020: 090afffe  beq r4,r5,0x2020
; STDOUT: 00002024: 290afffd  bne r4,r5,0x2020
; STDOUT: 00002028: 110afffc  bhs r4,r5,0x2020
; STDOUT: 0000202c: 310afffb  blo r4,r5,0x2020
; STDOUT: 00002030: 190afffa  blt r4,r5,0x2020
; STDOUT: 00002034: 390afff9  bge r4,r5,0x2020
; STDOUT: 00002038: 090bfff8  beqsq r4,r5,0x2020
; STDOUT: 0000203c: 390bfff7  bgesq r4,r5,0x2020
; STDOUT: 00002040: 0800fff6  b 0x2020
; STDOUT: 00002044: 310afff5  blo r4,r5,0x2020
; STDOUT: 00002048: 610a6019  add r4,r5,r6
; STDOUT: 0000204c: 610a6066  sub r4,r5,r6
; STDOUT: 00002050: 610a6026  subnc r4,r5,r6
; STDOUT: 00002054: 610a6023  and r4,r5,r6
; STDOUT: 00002058: 610a600b  bic r4,r5,r6
; STDOUT: 0000205c: 6100600f  not r4,r6
; STDOUT: 00002060: 610a603b  or r4,r5,r6
; STDOUT: 00002064: 610a601b  xor r4,r5,r6
; STDOUT: 00002068: 400a60e6  mstart r5,r6
; STDOUT: 0000206c: 418a6099  mstep r6,r5,r6
; STDOUT: 00002070: 418a6166  dstep r6,r5,r6
; STDOUT: 00002074: 490a60c0  rotlb r4,r5,r6
; STDOUT: 00002078: 490a6080  rotlcb r4,r5,r6
; STDOUT: 0000207c: 490a6268  sh r4,r5,r6,#5
; STDOUT: 00002080: 490a6201  sh r4,r5,r6,#32
; STDOUT: 00002084: 490a6278  sh r4,r5,r6,#1
; STDOUT: 00002088: 49006168  asr r4,r6,#5
; STDOUT: 0000208c: 480a6221  lsl r5,r6,#8
; STDOUT: 00002090: 49006261  lsr r4,r6,#8
; STDOUT: 00002094: 61006019  mov r4,r6
; STDOUT: 00002098: 60000019  nop
; STDOUT: 0000209c: e10dfff9  addi r4,#-7,r6
; STDOUT: 000020a0: e00cffff  addi r0,#65535,r6
; STDOUT: 000020a4: c5fe0010  jspci r23,#16,r31
; STDOUT: 000020a8: c7c00000  ret
; STDOUT: 000020ac: d8006001  movfrs psw,r6
; STDOUT: 000020b0: d8006002  movfrs md,r6
; STDOUT: 000020b4: d8006004  movfrs pcm4,r6
; STDOUT: 000020b8: d1000001  movtos r4,psw
; STDOUT: 000020bc: d1000002  movtos r4,md
; STDOUT: 000020c0: d1000004  movtos r4,pcm1
; STDOUT: 000020c4: e8000003  jpc
; STDOUT: 000020c8: f8000003  jpcrs
; STDOUT: 000020cc: cfc00000  hsc
; STDOUT: 000020d0: f00007fb  trap #0
; STDOUT: 000020d4: f000000b  trap #254
; STDOUT: 000020d8: 00000000  .word 0x00000000
_start:
    ld    4[r4],r5
    st    -4[r4],r5
    ldbu  1[r4],r5
    ldb   1[r4],r5
    ldhu  2[r4],r5
    ldh   2[r4],r5
    stb   3[r4],r5
    sth   2[r4],r5
0:  beq   r4,r5,0b
    bne   r4,r5,0b
    bhs   r4,r5,0b
    blo   r4,r5,0b
    blt   r4,r5,0b
    bge   r4,r5,0b
    beqsq r4,r5,0b
    bgesq r4,r5,0b
    b     0b
    bhi   r5,r4,0b
    add   r4,r5,r6
    sub   r4,r5,r6
    subnc r4,r5,r6
    and   r4,r5,r6
    bic   r4,r5,r6
    not   r4,r6
    or    r4,r5,r6
    xor   r4,r5,r6
    mstart r5,r6
    mstep r6,r5,r6
    dstep r6,r5,r6
    rotlb r4,r5,r6
    rotlcb r4,r5,r6
    sh    r4,r5,r6,#5
    sh    r4,r5,r6,#32
    sh    r4,r5,r6,#1
    asr   r4,r6,#5
    lsl   r5,r6,#8
    lsr   r4,r6,#8
    mov   r4,r6
    nop
    addi  r4,#-7,r6
    addi  r0,#0xFFFF,r6
    jspci r23,#16,r31
    ret
    movfrs psw,r6
    movfrs md,r6
    movfrs pcm4,r6
    movtos r4,psw
    movtos r4,md
    movtos r4,pcm1
    jpc
    jpcrs
    hsc
    trap  #0
    trap  #254
    .word 0
