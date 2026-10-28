#!/usr/bin/env python3
# Print code and data sizes of the third-party builds, attributed to
# each library from lld's map files (only what --gc-sections kept).
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
#   sizes.py [--markdown] [--detail PROG] BUILD_DIR...
#
# For each program, the bytes each archive (or object) contributes to
# .text, .rodata, .data (+.sdata) and .bss (+.sbss).  "flash" is
# text + rodata + data, "RAM" is data + bss.  lld merges string and
# constant sections (.rodata.str*, .rodata.cst*) across objects, so the
# map cannot attribute them; rodata adds those sections' pre-merge sizes
# from every archive member that was linked (an upper bound).

import argparse
import collections
import os
import re
import subprocess
import sys

PROGRAMS = [
    ("lwip_test", "liblwip.a", "lwIP (TCP, UDP, DHCP, DNS, ARP, httpd, SNTP, TFTP)"),
    ("lfs_test", "liblittlefs.a", "littlefs"),
    ("tls_client_min", "libbearssl.a", "BearSSL, minimal TLS 1.2 client"),
    ("tls_client_full", "libbearssl.a", "BearSSL, br_ssl_client_init_full"),
]
KINDS = {".text": "text", ".rodata": "rodata", ".data": "data", ".sdata": "data",
         ".bss": "bss", ".sbss": "bss"}

LINE = re.compile(r"^\s*([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+(\d+)\s(.*)$")


def owner(path):
    m = re.match(r"(.*?)\((.*)\)$", path)
    if m:
        return os.path.basename(m.group(1)), m.group(2)
    return os.path.basename(path), None


def parse_map(path):
    """Return {owner: {kind: bytes}} and {(owner, member): {kind: bytes}}."""
    by_lib = collections.defaultdict(collections.Counter)
    by_member = collections.defaultdict(collections.Counter)
    out = None
    with open(path) as f:
        next(f)
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            size = int(m.group(3), 16)
            rest = m.group(5)
            if not rest.startswith(" "):
                out = rest.strip()
                continue
            if out not in KINDS:
                continue
            text = rest.strip()
            m2 = re.match(r"(.*):\((.*)\)$", text)
            if not m2 or rest.startswith("         "):
                continue  # a symbol or an assignment, not an input section
            lib, member = owner(m2.group(1))
            if lib.endswith(".o") and member is None:
                lib = "program"
            by_lib[lib][KINDS[out]] += size
            by_member[(lib, member)][KINDS[out]] += size
    return by_lib, by_member


def merged_sizes(readelf, archive):
    """Return {member: bytes in mergeable rodata sections} for an archive."""
    out = subprocess.run([readelf, "-S", "-W", archive], capture_output=True,
                         text=True, check=True).stdout
    sizes = collections.Counter()
    member = None
    for line in out.splitlines():
        m = re.match(r"File: .*\((.*)\)$", line)
        if m:
            member = m.group(1)
            continue
        m = re.match(r"\s*\[\s*\d+\]\s+(\.rodata\.(?:str|cst)\S*)\s+PROGBITS\s+\S+\s+\S+\s+([0-9a-f]+)", line)
        if m and member:
            sizes[member] += int(m.group(2), 16)
    return sizes


def flash(c):
    return c["text"] + c["rodata"] + c["data"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--detail", help="per-object breakdown of one program")
    ap.add_argument("--readelf", default="llvm-readelf")
    ap.add_argument("dirs", nargs="+")
    args = ap.parse_args()

    if args.detail:
        for d in args.dirs:
            _, by_member = parse_map(os.path.join(d, args.detail + ".map"))
            print(f"== {d}/{args.detail}")
            for (lib, mem), c in sorted(by_member.items(), key=lambda kv: -flash(kv[1])):
                print(f"{flash(c):8d} {c['text']:8d} {c['rodata']:7d} {c['bss']:7d}  {lib}({mem})")
        return

    rows = []
    for prog, lib, desc in PROGRAMS:
        row = [desc]
        for d in args.dirs:
            by_lib, by_member = parse_map(os.path.join(d, prog + ".map"))
            c = by_lib.get(lib, collections.Counter())
            merged = merged_sizes(args.readelf, os.path.join(d, lib))
            c["rodata"] += sum(merged[mem] for (l, mem) in by_member if l == lib)
            rt = collections.Counter()
            for k in ("libc.a", "libbuiltins.a", "libm.a", "libsim.a", "crt0.o"):
                rt += by_lib.get(k, collections.Counter())
            row.append((c["text"], c["rodata"], c["data"], c["bss"], rt))
        rows.append(row)

    names = [os.path.basename(d.rstrip("/")) for d in args.dirs]
    if args.markdown:
        hdr = "| Component | " + " | ".join(
            f"{n} text | {n} rodata | {n} flash | {n} RAM" for n in names) + " |"
        print(hdr)
        print("|" + "---|" * (1 + 4 * len(names)))
        for row in rows:
            cells = [row[0]]
            for t, r, dd, b, _ in row[1:]:
                cells += [f"{t:,}", f"{r:,}", f"{t + r + dd:,}", f"{dd + b:,}"]
            print("| " + " | ".join(cells) + " |")
        return
    for row in rows:
        print(row[0])
        for n, (t, r, dd, b, rt) in zip(names, row[1:]):
            print(f"  {n:4s} text {t:7d}  rodata {r:6d}  data {dd:5d}  bss {b:6d}"
                  f"  flash {t + r + dd:7d}   (+ run-time libs flash {flash(rt):6d})")


if __name__ == "__main__":
    sys.exit(main())
