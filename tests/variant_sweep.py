#!/usr/bin/env python3
# Run executables under each simulator variant (tests/README.md).
# SPDX-License-Identifier: Apache-2.0
"""Show which unconfirmed processor facts compiled code depends on.

Runs every *.elf in the given directories on mipsx-sim, first as is and
then once per --variant (mipsx-sim --variant=list). Only programs that
pass (exit 0) as is take part. A program that no longer passes under a
variant depends on the fact that variant contradicts; one that still
passes either does not depend on it or does not exercise it.

  python3 tests/run_tests.py torture --llvm-bin ... --work build/sweep/torture
  python3 tests/variant_sweep.py build/sweep/torture --report sweep.md
"""

import argparse
import collections
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(HERE)


def variants(sim):
    out = subprocess.run([sim, "--variant=list"], capture_output=True,
                         text=True, check=True).stdout
    return [tuple(l.split(None, 1)) for l in out.splitlines() if l.strip()]


def run(sim, exe, variant, args):
    cmd = [sim, "--max-cycles=%d" % args.max_cycles]
    if variant:
        cmd.append("--variant=" + variant)
    try:
        p = subprocess.run(cmd + [exe], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=args.run_timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "wall clock"
    if p.returncode == 0:
        return "PASS", ""
    if p.returncode == 124:
        return "TIMEOUT", "cycle limit"
    if p.returncode == 125:
        m = re.search(r"mipsx-sim: error: (.*)", p.stderr)
        return "HAZARD", m.group(1) if m else p.stderr.strip()[-200:]
    return "FAIL", "exit %d" % p.returncode


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", help="directories of *.elf programs")
    ap.add_argument("--sim", default=os.path.join(SDK, "sim", "build", "mipsx-sim"))
    ap.add_argument("--variant", action="append",
                    help="only these variants (default: all)")
    ap.add_argument("-j", type=int, default=os.cpu_count())
    ap.add_argument("--max-cycles", type=int, default=1_000_000_000)
    ap.add_argument("--run-timeout", type=int, default=120)
    ap.add_argument("--examples", type=int, default=5,
                    help="programs to list per variant (default 5)")
    ap.add_argument("--results", help="write one line per program and variant")
    ap.add_argument("--report", help="write the summary as Markdown here")
    args = ap.parse_args()

    exes = sorted(os.path.join(d, f) for d in args.dirs
                  for f in os.listdir(d) if f.endswith(".elf"))
    if not exes:
        sys.exit("variant_sweep.py: no *.elf files")
    vs = variants(args.sim)
    if args.variant:
        known = dict(vs)
        bad = [v for v in args.variant if v not in known]
        if bad:
            sys.exit("variant_sweep.py: unknown variant " + " ".join(bad))
        vs = [(v, known[v]) for v in args.variant]

    with concurrent.futures.ThreadPoolExecutor(args.j) as pool:
        base = dict(zip(exes, pool.map(lambda e: run(args.sim, e, None, args),
                                       exes)))
        passing = [e for e in exes if base[e][0] == "PASS"]
        jobs = [(v, e) for v, _ in vs for e in passing]
        res = dict(zip(jobs, pool.map(
            lambda j: run(args.sim, j[1], j[0], args), jobs)))

    def name(exe):
        return os.path.relpath(exe)

    if args.results:
        with open(args.results, "w") as f:
            for e in exes:
                f.write("%s\t-\t%s\t%s\n" % ((name(e),) + base[e]))
            for (v, e), (status, detail) in sorted(res.items()):
                f.write("%s\t%s\t%s\t%s\n" % (name(e), v, status, detail))

    lines = ["# Variant sweep", "",
             "%d programs, %d pass without a variant (%s)." % (
                 len(exes), len(passing), ", ".join(args.dirs)), "",
             "| Variant | Affected | FAIL | HAZARD | TIMEOUT | What it assumes |",
             "|---|---|---|---|---|---|"]
    details = []
    for v, what in vs:
        bad = [(e, res[(v, e)]) for e in passing if res[(v, e)][0] != "PASS"]
        c = collections.Counter(s for _, (s, _) in bad)
        lines.append("| `%s` | %d (%.1f%%) | %d | %d | %d | %s |" % (
            v, len(bad), 100.0 * len(bad) / len(passing) if passing else 0,
            c["FAIL"], c["HAZARD"], c["TIMEOUT"], what))
        if bad:
            details += ["", "**%s**:" % v, ""]
            details += ["- `%s`: %s %s" % (name(e), s, d)
                        for e, (s, d) in bad[:args.examples]]
            if len(bad) > args.examples:
                details.append("- and %d more" % (len(bad) - args.examples))
    text = "\n".join(lines + details) + "\n"
    if args.report:
        with open(args.report, "w") as f:
            f.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
