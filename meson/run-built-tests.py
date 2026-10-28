#!/usr/bin/env python3
# Runs 'meson test' on the tests of a build directory whose programs were
# built, listing the others, so that a test program the compiler cannot
# build yet (docs/compiler-bugs/) does not stop the whole suite.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Use: run-built-tests.py BUILD_DIR [meson test options...]

import json
import os
import subprocess
import sys


def main(argv):
    build, opts = argv[1], argv[2:]
    meson = os.environ.get("MESON", "meson")
    tests = json.loads(subprocess.run(
        [meson, "introspect", "--tests", build], check=True,
        capture_output=True, text=True).stdout)
    built, missing = [], []
    for t in tests:
        files = [c for c in t["cmd"] if os.path.isabs(c)]
        (built if all(os.path.exists(f) for f in files) else missing).append(
            t["name"])
    for name in missing:
        print("not built: " + name)
    print("%d of %d tests built" % (len(built), len(tests)), flush=True)
    return subprocess.run([meson, "test", "-C", build, "--no-rebuild"] +
                          opts + built).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
