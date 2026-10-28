; mipsx-run --print-exit prints the status for FileCheck; other options
; go to the simulator.
; RUNNER: --print-exit --stats
; EXIT: 7
; STDOUT: A
; STDOUT: exit: 7
; STDERR: mipsx-sim: cycles
_start:
    addi  r0,#65,r4
    st    -65536[r0],r4
    addi  r0,#10,r4
    st    -65536[r0],r4
    exit  #7
