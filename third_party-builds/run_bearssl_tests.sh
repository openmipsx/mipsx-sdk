#!/bin/sh
# Run each of BearSSL's test_crypto tests on the simulator, in parallel,
# and print one line per test: name, result (pass, n/a for code this CPU cannot
# run, or FAIL with the exit status) and
# cycles.  Usage: run_bearssl_tests.sh SIM PROGRAM TEST_CRYPTO_C [JOBS]
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
sim=$1 prog=$2 src=$3 jobs=${4:-8}
sed -n 's/^[[:space:]]*STU(\([A-Za-z0-9_]*\)),$/\1/p' "$src" |
  xargs -P "$jobs" -I{} sh -c '
    out=$(echo {} | "$0" -c 20000000000 -s "$1" 2>&1); st=$?
    cyc=$(echo "$out" | sed -n "s/.*cycles \([0-9]*\),.*/\1/p")
    if [ $st -eq 0 ] && echo "$out" | grep -q "UNAVAILABLE"; then r=n/a
    elif [ $st -eq 0 ] && echo "$out" | grep -q "done\."; then r=pass
    else r="FAIL($st)"; fi
    note=$(echo "$out" | grep -v "^mipsx-sim:" | grep -iv "done\.\|unavailable\|^Test " | head -1)
    printf "%-24s %-9s %12s %s\n" {} "$r" "$cyc" "$note"' "$sim" "$prog" |
  sort
