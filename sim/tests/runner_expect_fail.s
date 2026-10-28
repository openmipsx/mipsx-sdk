; mipsx-run --expect-exit with a different status fails with 1.
; RUNNER: --expect-exit=4
; EXIT: 1
; STDERR: mipsx-run: program exited with status 3, expected 4
_start:
    exit  #3
