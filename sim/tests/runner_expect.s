; mipsx-run --expect-exit turns a matching status into 0.
; RUNNER: --expect-exit=3
; EXIT: 0
_start:
    exit  #3
