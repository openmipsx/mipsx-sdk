#!/usr/bin/env python3
# Tests for the multiply, divide and shift helpers (rt/builtins/*.S) on the
# simulator, against a reference computed here with C semantics.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# For each helper this generates a test program: a table of argument
# words and expected result words in .rodata, and a main that calls the
# helper on every row and checks
#   - the result (r2, and r3 for 64-bit results),
#   - every register the helper promises to preserve: the callee-saved
#     ones, sp, r23/r24/r28, and the caller-saved ones outside its
#     documented clobber set (CLOBBERS below, as in rt/builtins/README.md),
# and prints the cycles each call took.  The program is assembled and
# linked with crt0 by sim/tests/mxasm.py (until llvm-mc and lld exist) and
# run on mipsx-sim, which also stops on any pipeline hazard (abi §9).
#
# From the repository root:
#     python3 -m unittest discover -s rt/tests -t rt/tests   (all rt tests)
#     python3 rt/tests/test_builtins.py --cycles   (cycle table, no tests)
# $MIPSX_SIM overrides the simulator (default sim/build/mipsx-sim).

import os
import random
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
sys.path.insert(0, os.path.join(ROOT, "sim", "tests"))
import mxasm  # noqa: E402

SIM = os.environ.get("MIPSX_SIM",
                     os.path.join(ROOT, "sim", "build", "mipsx-sim"))
RT = os.path.join(ROOT, "rt")
BUILTINS = os.path.join(RT, "builtins")

M32 = (1 << 32) - 1
M64 = (1 << 64) - 1


def s32(x):
    x &= M32
    return x - (1 << 32) if x >> 31 else x


def s64(x):
    x &= M64
    return x - (1 << 64) if x >> 63 else x


def tdiv(n, d):
    """C division: truncated; n / 0 = 0 (our choice, see divsi3.S)."""
    if d == 0:
        return 0
    q = abs(n) // abs(d)
    return -q if (n < 0) != (d < 0) else q


def tmod(n, d):
    return n if d == 0 else n - tdiv(n, d) * d


def split(x):
    return [(x >> 32) & M32, x & M32]


# name -> (source files, argument kinds, result words, reference, clobbers)
# Argument kinds: "w" a 32-bit word, "d" a 64-bit value (two words, high
# first).  The reference takes unsigned Python ints and returns the result
# as an unsigned int.  Clobbers: registers the helper may change besides
# r31 and MD (rt/builtins/README.md).
R1_3 = {1, 2, 3}
R1_5 = {1, 2, 3, 4, 5}
ROUTINES = {
    "__mulsi3": (["mulsi3.S"], "ww", 1,
                 lambda a, b: (a * b) & M32, R1_3),
    "__udivsi3": (["divsi3.S"], "ww", 1,
                  lambda a, b: a // b if b else 0, R1_3),
    "__umodsi3": (["divsi3.S"], "ww", 1,
                  lambda a, b: a % b if b else a, R1_3 | {15}),
    "__divsi3": (["divsi3.S"], "ww", 1,
                 lambda a, b: tdiv(s32(a), s32(b)) & M32,
                 R1_5 | {12, 13, 15}),
    "__modsi3": (["divsi3.S"], "ww", 1,
                 lambda a, b: tmod(s32(a), s32(b)) & M32,
                 R1_5 | {12, 13, 15}),
    "__muldi3": (["muldi3.S", "mulsi3.S"], "dd", 2,
                 lambda a, b: (a * b) & M64,
                 R1_5 | set(range(8, 16))),
    "__udivdi3": (["divdi3.S"], "dd", 2,
                  lambda a, b: a // b if b else 0,
                  R1_5 | set(range(6, 12))),
    "__umoddi3": (["divdi3.S"], "dd", 2,
                  lambda a, b: a % b if b else a,
                  R1_5 | set(range(6, 12)) | {15}),
    "__divdi3": (["divdi3.S"], "dd", 2,
                 lambda a, b: tdiv(s64(a), s64(b)) & M64,
                 R1_5 | set(range(6, 14)) | {15}),
    "__moddi3": (["divdi3.S"], "dd", 2,
                 lambda a, b: tmod(s64(a), s64(b)) & M64,
                 R1_5 | set(range(6, 14)) | {15}),
    "__ashlsi3": (["ashl.S"], "ww", 1,
                  lambda a, n: (a << (n & 31)) & M32, R1_3 | {5}),
    "__lshrsi3": (["lshr.S"], "ww", 1,
                  lambda a, n: a >> (n & 31), R1_3),
    "__ashrsi3": (["ashr.S"], "ww", 1,
                  lambda a, n: (s32(a) >> (n & 31)) & M32, R1_3),
    "__ashldi3": (["ashl.S"], "dw", 2,
                  lambda a, n: (a << (n & 63)) & M64, R1_5),
    "__lshrdi3": (["lshr.S"], "dw", 2,
                  lambda a, n: a >> (n & 63), R1_5),
    "__ashrdi3": (["ashr.S"], "dw", 2,
                  lambda a, n: (s64(a) >> (n & 63)) & M64, R1_5),
}

# -- inputs ----------------------------------------------------------------


def edge_values(bits):
    """0, ±1, ±2, ±3, the extremes, every power of two with its
    neighbours and their negations, and some patterns, as unsigned."""
    m = (1 << bits) - 1
    v = {0, 1, 2, 3, 5, 7, 10, 100, 1000, 0x7F, 0x80, 0xFF, 0x100,
         0x7FFF, 0x8000, 0xFFFF, 0x10000, 0x12345678, 0xDEADBEEF,
         0x55555555, 0xAAAAAAAA}
    if bits == 64:
        v |= {0x123456789ABCDEF0, 0xFEDCBA9876543210, 0x5555555555555555,
              0xFFFFFFFF, 0x100000000, 0x1FFFFFFFF, 0xFFFFFFFF00000000,
              0x7FFFFFFF80000000}
    for k in range(bits):
        v |= {1 << k, (1 << k) - 1, (1 << k) + 1}
    v |= {-x & m for x in list(v)}
    return sorted(x & m for x in v)


def core_values(bits):
    """A smaller set for the full cross product of two-operand helpers."""
    m = (1 << bits) - 1
    v = {0, 1, 2, 3, 7, 10, 0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000,
         0xFFFF, 0x10000, 0x12345678, 0xDEADBEEF}
    ks = range(bits) if bits == 32 else \
        [0, 1, 7, 8, 15, 16, 23, 30, 31, 32, 33, 47, 48, 62, 63]
    for k in ks:
        v.add(1 << k)
    for k in ([7, 8, 15, 16, 30, 31] if bits == 32 else
              [15, 16, 31, 32, 33, 62, 63]):
        v |= {(1 << k) - 1, (1 << k) + 1}
    v |= {-x & m for x in list(v)}
    return sorted(x & m for x in v)


def random_value(rng, bits):
    """A value with a random number of significant bits, either sign, so
    that the short paths and the general ones are all exercised."""
    n = rng.randint(0, bits)
    x = rng.getrandbits(n) if n else 0
    if rng.random() < 0.3:
        x = -x
    return x & ((1 << bits) - 1)


def cases(name, seed=12345):
    """The (args, expected) rows for NAME: args are unsigned ints, one per
    argument (64-bit for kind 'd')."""
    _, kinds, _, ref, _ = ROUTINES[name]
    rng = random.Random(seed)
    rows = []
    if kinds[1] == "w" and "sh" in name:          # shifts
        bits = 32 if kinds[0] == "w" else 64
        for x in edge_values(bits):
            for n in range(bits):
                rows.append((x, n))
        for _ in range(1000):
            rows.append((rng.getrandbits(bits), rng.randrange(bits)))
        # Out-of-range amounts: only the low 5 (6) bits count.
        for n in [bits, bits + 1, 2 * bits - 1, 255, 256, 0x7FFFFFFF,
                  0x80000000, M32]:
            for x in [1, M32 if bits == 32 else M64, 0x12345678]:
                rows.append((x, n))
    else:                                         # two operands
        bits = 32 if kinds == "ww" else 64
        core = core_values(bits)
        edge = edge_values(bits)
        for a in core:
            for b in core:
                rows.append((a, b))
        few = [0, 1, M32 if bits == 32 else M64, 2, 3, 10, 1 << (bits - 1),
               (1 << (bits - 1)) - 1]
        for a in edge:
            for b in few:
                rows.append((a, b))
                rows.append((b, a))
        for _ in range(3000):
            rows.append((random_value(rng, bits), random_value(rng, bits)))
    return [(args, ref(*args)) for args in rows]


# -- the test program -------------------------------------------------------

# Registers the test main sets to canaries and checks after each call,
# unless the helper may clobber them or they are argument registers.
# r16 holds the row pointer (checked against memory), r20 the start time;
# r23, r24, r28 and sp are checked against their values at start-up.
CHECKED = [r for r in range(1, 31)
           if r not in (16, 20, 23, 24, 28, 29)]


def canary(r):
    return -30000 - 7 * r


def program(name, rows):
    """Assembly for main: checks NAME on ROWS."""
    _, kinds, nres, _, clobbers = ROUTINES[name]
    assert 1 in clobbers, "r1 is the scratch register of the checks"
    nwords = sum(2 if k == "d" else 1 for k in kinds)
    stride = 4 * (nwords + nres)
    L = []
    a = L.append
    a("    .text")
    a("    .globl  main")
    a("main:")
    a("    la      .Lsp_save,r1")
    a("    st      0[r1],sp")
    a("    la      .Lrows,r16")
    a(".Lloop:")
    a("    la      .Lrow,r1")
    a("    st      0[r1],r16")
    a("    la      .Lrows_end,r1")
    a("    beq     r16,r1,.Ldone")
    a("    nop")
    a("    nop")
    for i in range(nwords):
        a("    ld      %d[r16],r%d" % (4 * i, 4 + i))
    for r in CHECKED:
        if r >= 4 + nwords or r < 4:
            a("    addi    r0,#%d,r%d" % (canary(r), r))
    a("    ld      -65528[r0],r20      ; cycle counter")
    a("    call    %s" % name)
    a("    nop")
    a("    nop")
    a("    ld      -65528[r0],r31")
    # Checks; r1 is the scratch register and, after a failed branch, the
    # number of the check.
    a("    nop")
    a("    sub     r31,r20,r31         ; cycles + 4; r20 is free now")
    a("    la      .Lrow,r20")
    a("    ld      0[r20],r1")
    a("    nop")
    a("    bne     r16,r1,.Lfail")
    a("    addi    r0,#16,r1")
    a("    nop")
    a("    la      .Lsp_save,r20")
    a("    ld      0[r20],r1")
    a("    nop")
    a("    bne     sp,r1,.Lfail")
    a("    addi    r0,#29,r1")
    a("    nop")
    for r, sym in ((23, "__mipsx_cb0"), (24, "__mipsx_cb1")):
        a("    la      %s,r1" % sym)
        a("    lsr     r1,r1,#2")
        a("    bne     r%d,r1,.Lfail" % r)
        a("    addi    r0,#%d,r1" % r)
        a("    nop")
    a("    la      _gp,r1")
    a("    bne     gp,r1,.Lfail")
    a("    addi    r0,#28,r1")
    a("    nop")
    for r in CHECKED:
        if r in clobbers:
            continue
        if 4 <= r < 4 + nwords:
            a("    ld      %d[r16],r1" % (4 * (r - 4)))
            a("    nop")
        else:
            a("    addi    r0,#%d,r1" % canary(r))
        a("    bne     r%d,r1,.Lfail" % r)
        a("    addi    r0,#%d,r1" % r)
        a("    nop")
    for i in range(nres):
        a("    ld      %d[r16],r1" % (4 * (nwords + i)))
        a("    nop")
        a("    bne     r%d,r1,.Lfail" % (2 + i))
        a("    addi    r0,#%d,r1" % (100 + i))
        a("    nop")
    a("    mov     r31,r4")
    a("    call    .Lputhex")
    a("    nop")
    a("    nop")
    a("    addi    r0,#10,r4")
    a("    stb     -65536[r0],r4")
    a("    b       .Lloop")
    a("    addi    r16,#%d,r16" % stride)
    a("    nop")
    a(".Ldone:")
    a("    mov     r0,r4")
    a("    call    exit")
    a("    nop")
    a("    nop")
    # Failure: print "FAIL check row r2 r3" in hex and exit 1.
    a(".Lfail:")
    a("    mov     r1,r25")
    a("    mov     r2,r26")
    a("    mov     r3,r27")
    a("    la      .Lfailmsg,r17")
    a("1:  ldbu    0[r17],r4")
    a("    addi    r17,#1,r17")
    a("    beq     r4,r0,2f")
    a("    nop")
    a("    nop")
    a("    b       1b")
    a("    stb     -65536[r0],r4")
    a("    nop")
    a("2:")
    for reg in ("r25", "r16", "r26", "r27"):
        a("    addi    r0,#32,r4")
        a("    stb     -65536[r0],r4")
        a("    mov     %s,r4" % reg)
        a("    call    .Lputhex")
        a("    nop")
        a("    nop")
    a("    addi    r0,#10,r4")
    a("    stb     -65536[r0],r4")
    a("    addi    r0,#1,r4")
    a("    call    exit")
    a("    nop")
    a("    nop")
    # Print r4 as 8 hex digits; clobbers r4, r8, r9, r10.
    a(".Lputhex:")
    a("    addi    r0,#8,r8")
    a("1:  lsr     r4,r9,#28")
    a("    addi    r9,#48,r9")
    a("    addi    r0,#58,r10")
    a("    bhssq   r9,r10,2f           ; a-f: run the slots")
    a("    addi    r9,#39,r9")
    a("    nop")
    a("2:  stb     -65536[r0],r9")
    a("    addi    r8,#-1,r8")
    a("    bne     r8,r0,1b")
    a("    lsl     r4,r4,#4")
    a("    nop")
    a("    ret")
    a("    nop")
    a("    nop")
    a("    .section .rodata")
    a(".Lfailmsg:")
    a('    .asciz  "FAIL"')
    a("    .p2align 2")
    a(".Lrows:")
    for args, res in rows:
        words = []
        for k, x in zip(kinds, args):
            words += split(x) if k == "d" else [x & M32]
        words += split(res) if nres == 2 else [res]
        a("    .word   " + ",".join("0x%x" % w for w in words))
    a(".Lrows_end:")
    a("    .bss")
    a("    .p2align 2")
    a(".Lrow:")
    a("    .space  4")
    a(".Lsp_save:")
    a("    .space  4")
    return "\n".join(L) + "\n"


def read(path):
    with open(path) as f:
        return f.read()


class Result:
    def __init__(self, status, out, err, cycles, failure):
        self.status, self.out, self.err = status, out, err
        self.cycles, self.failure = cycles, failure


def run_routine(name, rows, tmpdir):
    files, kinds, nres, _, _ = ROUTINES[name]
    paths = [os.path.join(RT, "crt0.S"), os.path.join(RT, "exit-sim.S"),
             os.path.join(RT, "args-sim.S")] + \
        [os.path.join(BUILTINS, f) for f in files]
    texts = [read(p) for p in paths] + [program(name, rows)]
    elf = os.path.join(tmpdir, name + ".elf")
    asm = mxasm.link(texts, elf, names=paths + ["main"])
    p = subprocess.run([SIM, elf], capture_output=True, timeout=600)
    out = p.stdout.decode("latin-1")
    err = p.stderr.decode("utf-8", "replace")
    cycles, failure = [], None
    for line in out.splitlines():
        m = re.fullmatch(r"FAIL ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{8}) "
                         r"([0-9a-f]{8})", line)
        if m:
            check, addr, r2, r3 = (int(g, 16) for g in m.groups())
            nwords = sum(2 if k == "d" else 1 for k in kinds)
            row = (addr - asm.labels[".L%d_rows" % (len(texts) - 1)]) // \
                (4 * (nwords + nres))
            failure = (check, row, r2, r3)
        elif re.fullmatch(r"[0-9a-f]{8}", line):
            cycles.append(int(line, 16) - 4)
    return Result(p.returncode, out, err, cycles, failure)


def describe_failure(name, rows, failure):
    check, row, r2, r3 = failure
    args, res = rows[row]
    what = {100: "r2 (result)", 101: "r3 (result)"}.get(
        check, "r%d (should be preserved)" % check)
    return ("%s(%s): row %d, wrong %s; expected %s, got r2=0x%08x "
            "r3=0x%08x" % (name, ", ".join("0x%x" % x for x in args), row,
                           what, "0x%x" % res, r2, r3))


@unittest.skipUnless(os.path.exists(SIM), "simulator not built")
class BuiltinsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, name):
        rows = cases(name)
        r = run_routine(name, rows, self.tmp.name)
        if r.failure:
            self.fail(describe_failure(name, rows, r.failure))
        self.assertEqual(r.err, "", "simulator diagnostics")
        self.assertEqual(r.status, 0)
        self.assertEqual(len(r.cycles), len(rows))


def _make_test(name):
    return lambda self: self.check(name)


for _name in ROUTINES:
    setattr(BuiltinsTest, "test" + _name, _make_test(_name))


def cycle_table():
    """Prints rows, min, max and mean cycles per helper."""
    with tempfile.TemporaryDirectory() as tmp:
        print("%-12s %6s %5s %5s %7s" % ("helper", "rows", "min", "max",
                                         "mean"))
        for name in ROUTINES:
            rows = cases(name)
            r = run_routine(name, rows, tmp)
            if r.failure or r.status:
                print("%-12s FAILED (status %d) %s" % (name, r.status,
                      describe_failure(name, rows, r.failure)
                      if r.failure else r.err.strip()))
                continue
            c = r.cycles
            print("%-12s %6d %5d %5d %7.1f" % (name, len(c), min(c), max(c),
                                               sum(c) / len(c)))


if __name__ == "__main__":
    if sys.argv[1:] == ["--cycles"]:
        cycle_table()
    else:
        unittest.main()
