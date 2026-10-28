#!/usr/bin/env python3
# Minimal MIPS-X (ES3890) assembler and ELF writer for the simulator tests.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# This is not the real assembler (that is LLVM's, work packages S2-S4).
# It encodes instructions straight from processor-es3890.md §2-§6, with
# the syntax of abi.md §10, independently of the simulator's decoder, and
# writes a linked big-endian ELF32 executable (abi §11).
#
# Source format: one statement per line, ';' comments, 'label:' prefixes.
#   Instructions and pseudo-instructions of abi §10.3 and §10.5
#   (nop mov lsl lsr li la b ret call jmp bgt ble bhi bls ...).
#   Directives: .org ADDR (byte address, forward only; pads with zero
#   words), .word EXPR[,EXPR...], .space N, .align N (2^N bytes),
#   .ascii "text" / .asciz "text", .rept N / .endr.
#   Test-only pseudo: 'expect rN,VALUE' branches to a stub that exits with
#   the source line number (mod 256) if rN != VALUE; it clobbers r1.
#   'exit #N' stores N to the exit register (clobbers r1).
# Expressions: integers, labels (byte addresses), '.', + and -, and the
# operators %hi() %lo() %w() of abi §10.6 (evaluated at assembly time).

import re
import struct
import sys

EM_MIPS_X = 51
IO_PUTCHAR = -0x10000
IO_EXIT = -0x10000 + 4

REGALIAS = {"zero": 0, "at": 1, "cb0": 23, "cb1": 24, "gp": 28, "sp": 29,
            "fp": 30, "ra": 31}
SPECIAL = {"psw": 1, "md": 2, "pcm4": 4, "pcm1": 4}

MEM_OPS = {"ld": 0, "ldhu": 1, "st": 2, "stb": 3, "ldbu": 4, "ldb": 5,
           "sth": 6, "ldh": 7}
LOADS = {"ld", "ldhu", "ldbu", "ldb", "ldh"}
BRANCH_CONDS = {"beq": 1, "bhs": 2, "blt": 3, "bne": 5, "blo": 6, "bge": 7}
SWAPPED = {"bgt": "blt", "ble": "bge", "bhi": "blo", "bls": "bhs"}
ALU3 = {"add": 0x019, "sub": 0x066, "subnc": 0x026, "and": 0x023,
        "bic": 0x00B, "or": 0x03B, "xor": 0x01B}


class AsmError(Exception):
    pass


def reg(tok):
    t = tok.strip().lower()
    if t in REGALIAS:
        return REGALIAS[t]
    m = re.fullmatch(r"r(\d+)", t)
    if not m or int(m.group(1)) > 31:
        raise AsmError("bad register %r" % tok)
    return int(m.group(1))


def split_operands(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def shift_func(n, asr):
    if not 1 <= n <= 32:
        raise AsmError("shift amount %d out of range 1-32" % n)
    e = 32 - n
    return (0x100 if asr else 0x200) | ((e >> 2) << 4) | (1 << (e & 3))


def li_words(value, rd):
    """abi §6.1 constant sequence, as (mnemonic, operands) tuples."""
    v = value & 0xFFFFFFFF
    sv = v - (1 << 32) if v & 0x80000000 else v
    if -0x10000 <= sv <= 0xFFFF:
        return [("addi", "r0,#%d,r%d" % (sv, rd))]
    t = (v & -v).bit_length() - 1 if v else 0
    s = sv >> t
    if t and -0x10000 <= s <= 0xFFFF:
        return [("addi", "r0,#%d,r%d" % (s, rd)),
                ("lsl", "r%d,r%d,#%d" % (rd, rd, t))]
    hi = sv >> 15
    lo = v & 0x7FFF
    return [("addi", "r0,#%d,r%d" % (hi, rd)),
            ("lsl", "r%d,r%d,#15" % (rd, rd)),
            ("addi", "r%d,#%d,r%d" % (rd, lo, rd))]


class Assembler:
    def __init__(self, base=0x2000):
        self.base = base
        self.items = []      # (addr, kind, payload, lineno)
        self.labels = {}
        self.expects = []
        self.local_count = {}

    # -- expressions ------------------------------------------------------
    def eval(self, expr, pc, final):
        """Evaluates EXPR: numbers, symbols, '.', parentheses, unary and
        binary + and -, and %hi() %lo() %w()."""
        e = expr.strip()
        if e.startswith("#"):
            e = e[1:].strip()
        toks = re.findall(r"0[xX][0-9a-fA-F]+|\d+|%(?:hi|lo|w)\(|"
                          r"[A-Za-z_.$][\w.$]*|[-+()]|\S", e)
        pos = [0]

        def peek():
            return toks[pos[0]] if pos[0] < len(toks) else None

        def take():
            t = peek()
            if t is None:
                raise AsmError("bad expression %r" % expr)
            pos[0] += 1
            return t

        def primary():
            t = take()
            if t == "-":
                return -primary()
            if t == "+":
                return primary()
            if t == "(" or t.startswith("%"):
                v = sum_()
                if take() != ")":
                    raise AsmError("bad expression %r" % expr)
                if t == "%hi(":
                    v &= 0xFFFFFFFF
                    v = (v - (1 << 32) if v & 0x80000000 else v) >> 15
                elif t == "%lo(":
                    v &= 0x7FFF
                elif t == "%w(":
                    if final and v & 3:
                        raise AsmError("%%w of unaligned value 0x%x" % v)
                    v >>= 2
                return v
            if re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", t):
                return int(t, 0)
            if t == ".":
                return pc
            if re.fullmatch(r"[A-Za-z_.$][\w.$]*", t):
                if t in self.labels:
                    return self.labels[t]
                if final:
                    raise AsmError("undefined symbol %r" % t)
                return 0
            raise AsmError("bad expression %r" % expr)

        def sum_():
            v = primary()
            while peek() in ("+", "-"):
                v = v + primary() if take() == "+" else v - primary()
            return v

        v = sum_()
        if peek() is not None:
            raise AsmError("bad expression %r" % expr)
        return v

    # -- parsing -----------------------------------------------------------
    def parse(self, text):
        pc = self.base
        for lineno, raw in self.expand_rept(text):
            line = raw
            # strip comments (';' outside strings)
            out, instr = "", False
            for ch in line:
                if ch == '"':
                    instr = not instr
                if ch == ";" and not instr:
                    break
                out += ch
            line = out.strip()
            while True:
                m = re.match(r"(\d+)\s*:\s*(.*)$", line)
                if m:  # numeric local label
                    n = m.group(1)
                    k = self.local_count.get(n, 0) + 1
                    self.local_count[n] = k
                    line = "__L%s_%d: %s" % (n, k, m.group(2))
                m = re.match(r"([A-Za-z_.$][\w.$]*)\s*:\s*(.*)$", line)
                if not m:
                    break
                if m.group(1) in self.labels:
                    raise AsmError("line %d: duplicate label %s"
                                   % (lineno, m.group(1)))
                self.labels[m.group(1)] = pc
                line = m.group(2).strip()
            if not line:
                continue
            parts = line.split(None, 1)
            mnem = parts[0].lower()
            ops = parts[1] if len(parts) > 1 else ""

            def local_ref(m):
                n, d = m.group(1), m.group(2)
                k = self.local_count.get(n, 0)
                return "__L%s_%d" % (n, k + 1 if d == "f" else k)
            ops = re.sub(r"(?<![\w.$])(\d+)([fb])(?![\w.$])", local_ref, ops)
            try:
                pc = self.statement(mnem, ops, pc, lineno)
            except AsmError as ex:
                raise AsmError("line %d: %s" % (lineno, ex))
        if self.expects:
            pc = (pc + 3) & ~3
            for (label, lineno) in self.expects:
                self.labels[label] = pc
                for m_, o_ in [("addi", "r0,#%d,r1" % (lineno & 0xFF)),
                               ("st", "%d[r0],r1" % IO_EXIT)]:
                    self.items.append((pc, "insn", (m_, o_), lineno))
                    pc += 4
        self.end = pc

    def li_seq(self, expr, rd, pc):
        try:
            return li_words(self.eval(expr, pc, True), rd)
        except AsmError:  # forward reference: always three words
            return [("addi", "r0,#%%hi(%s),r%d" % (expr, rd)),
                    ("lsl", "r%d,r%d,#15" % (rd, rd)),
                    ("addi", "r%d,#%%lo(%s),r%d" % (rd, expr, rd))]

    @staticmethod
    def expand_rept(text):
        """Expands '.rept N' ... '.endr' blocks (not nested)."""
        out, block, count = [], None, 0
        for lineno, raw in enumerate(text.splitlines(), 1):
            words = raw.split(";")[0].split()
            if words and words[0].lower() == ".rept":
                block, count = [], int(words[1], 0)
                continue
            if words and words[0].lower() == ".endr":
                out += block * count
                block = None
                continue
            (out if block is None else block).append((lineno, raw))
        return out

    def statement(self, mnem, ops, pc, lineno):
        if mnem == ".org":
            addr = self.eval(ops, pc, True)
            if addr < pc:
                raise AsmError(".org backwards")
            while pc < addr:
                self.items.append((pc, "word", "0", lineno))
                pc += 4
            return pc
        if mnem == ".word":
            for e in split_operands(ops):
                self.items.append((pc, "word", e, lineno))
                pc += 4
            return pc
        if mnem == ".space":
            n = self.eval(ops, pc, True)
            self.items.append((pc, "bytes", bytes(n), lineno))
            return pc + n
        if mnem == ".align":
            a = 1 << self.eval(ops, pc, True)
            n = (-pc) % a
            if n:
                self.items.append((pc, "bytes", bytes(n), lineno))
            return pc + n
        if mnem in (".ascii", ".asciz"):
            m = re.fullmatch(r'"(.*)"', ops.strip())
            if not m:
                raise AsmError("bad string")
            data = m.group(1).encode().decode("unicode_escape").encode("latin-1")
            if mnem == ".asciz":
                data += b"\0"
            self.items.append((pc, "bytes", data, lineno))
            return pc + len(data)
        if pc & 3:
            raise AsmError("instruction at unaligned address 0x%x" % pc)
        # pseudo-instructions that expand to several words
        if mnem == "li":
            a = split_operands(ops)
            for m_, o_ in self.li_seq(a[0], reg(a[1]), pc):
                self.items.append((pc, "insn", (m_, o_), lineno))
                pc += 4
            return pc
        if mnem == "la":
            a = split_operands(ops)
            rd = reg(a[1])
            for m_, o_ in [("addi", "r0,#%%hi(%s),r%d" % (a[0], rd)),
                           ("lsl", "r%d,r%d,#15" % (rd, rd)),
                           ("addi", "r%d,#%%lo(%s),r%d" % (rd, a[0], rd))]:
                self.items.append((pc, "insn", (m_, o_), lineno))
                pc += 4
            return pc
        if mnem == "expect":
            a = split_operands(ops)
            label = "__expect_fail_%d" % len(self.expects)
            self.expects.append((label, lineno))
            seq = self.li_seq(a[1], 1, pc) + [("bne", "%s,r1,%s" % (a[0], label)),
                                        ("nop", ""), ("nop", "")]
            for m_, o_ in seq:
                self.items.append((pc, "insn", (m_, o_), lineno))
                pc += 4
            return pc
        if mnem == "exit":
            value = self.eval(ops, pc, True)
            for m_, o_ in li_words(value, 1) + [("st", "%d[r0],r1" % IO_EXIT)]:
                self.items.append((pc, "insn", (m_, o_), lineno))
                pc += 4
            return pc
        self.items.append((pc, "insn", (mnem, ops), lineno))
        return pc + 4

    # -- encoding ----------------------------------------------------------
    def encode(self, mnem, ops, pc):
        a = split_operands(ops)
        ev = lambda e: self.eval(e, pc, True)

        def imm17(v):
            if not -0x10000 <= v <= 0xFFFF:
                raise AsmError("immediate %d out of 17-bit range" % v)
            return v & 0x1FFFF

        def nargs(n):
            if len(a) != n:
                raise AsmError("%s takes %d operands" % (mnem, n))

        if mnem in MEM_OPS:
            nargs(2)
            m = re.fullmatch(r"(.*)\[(.+)\]", a[0])
            if not m:
                raise AsmError("bad memory operand %r" % a[0])
            off = ev(m.group(1)) if m.group(1).strip() else 0
            return (2 << 30 | MEM_OPS[mnem] << 27 | reg(m.group(2)) << 22 |
                    reg(a[1]) << 17 | imm17(off))
        base = mnem[:-2] if mnem.endswith("sq") else mnem
        sq = 1 if mnem.endswith("sq") and base != mnem else 0
        if base in SWAPPED:
            nargs(3)
            return self.encode(SWAPPED[base] + ("sq" if sq else ""),
                               "%s,%s,%s" % (a[1], a[0], a[2]), pc)
        if base in BRANCH_CONDS or base in ("b", "bra"):
            if base in ("b", "bra"):
                nargs(1)
                s1 = s2 = 0
                cond = 1
                target = a[0]
            else:
                nargs(3)
                s1, s2, cond, target = reg(a[0]), reg(a[1]), BRANCH_CONDS[base], a[2]
            t = ev(target)
            if t & 3:
                raise AsmError("unaligned branch target")
            disp = t // 4 - (pc // 4 + 2)
            if not -0x8000 <= disp <= 0x7FFF:
                raise AsmError("branch out of range")
            return 0 << 30 | cond << 27 | s1 << 22 | s2 << 17 | sq << 16 | (disp & 0xFFFF)
        if mnem == "nop":
            return 0x60000019
        if mnem in ALU3:
            nargs(3)
            return 1 << 30 | 4 << 27 | reg(a[0]) << 22 | reg(a[1]) << 17 | reg(a[2]) << 12 | ALU3[mnem]
        if mnem == "mov":
            nargs(2)
            return 1 << 30 | 4 << 27 | reg(a[0]) << 22 | reg(a[1]) << 12 | 0x019
        if mnem == "not":
            nargs(2)
            return 1 << 30 | 4 << 27 | reg(a[0]) << 22 | reg(a[1]) << 12 | 0x00F
        if mnem == "mstart":
            nargs(2)
            return 1 << 30 | 0 << 27 | reg(a[0]) << 17 | reg(a[1]) << 12 | 0x0E6
        if mnem in ("mstep", "dstep"):
            nargs(3)
            f = 0x099 if mnem == "mstep" else 0x166
            return 1 << 30 | 0 << 27 | reg(a[0]) << 22 | reg(a[1]) << 17 | reg(a[2]) << 12 | f
        if mnem in ("rotlb", "rotlcb"):
            nargs(3)
            f = 0x0C0 if mnem == "rotlb" else 0x080
            return 1 << 30 | 1 << 27 | reg(a[0]) << 22 | reg(a[1]) << 17 | reg(a[2]) << 12 | f
        if mnem == "sh":
            nargs(4)
            return (1 << 30 | 1 << 27 | reg(a[0]) << 22 | reg(a[1]) << 17 |
                    reg(a[2]) << 12 | shift_func(ev(a[3]), False))
        if mnem == "asr":
            nargs(3)
            return (1 << 30 | 1 << 27 | reg(a[0]) << 22 | reg(a[1]) << 12 |
                    shift_func(ev(a[2]), True))
        if mnem == "lsl":  # sh r0,rs,rd,#(32-k)
            nargs(3)
            k = ev(a[2])
            if not 0 <= k <= 31:
                raise AsmError("lsl amount out of range")
            return (1 << 30 | 1 << 27 | reg(a[0]) << 17 | reg(a[1]) << 12 |
                    shift_func(32 - k, False))
        if mnem == "lsr":  # sh rs,r0,rd,#k
            nargs(3)
            return (1 << 30 | 1 << 27 | reg(a[0]) << 22 | reg(a[1]) << 12 |
                    shift_func(ev(a[2]), False))
        if mnem in ("addi", "jspci"):
            nargs(3)
            op = 4 if mnem == "addi" else 0
            return 3 << 30 | op << 27 | reg(a[0]) << 22 | reg(a[2]) << 17 | imm17(ev(a[1]))
        if mnem == "ret":
            return self.encode("jspci", "r31,#0,r0", pc)
        if mnem in ("call", "jmp"):
            nargs(1)
            # Absolute word address through r0 (what R_MIPSX_CALL17 picks
            # for targets below 256 KB).
            rd = "r31" if mnem == "call" else "r0"
            return self.encode("jspci", "r0,#%%w(%s),%s" % (a[0], rd), pc)
        if mnem == "movfrs":
            nargs(2)
            return 3 << 30 | 3 << 27 | reg(a[1]) << 12 | SPECIAL[a[0].lower()]
        if mnem == "movtos":
            nargs(2)
            return 3 << 30 | 2 << 27 | reg(a[0]) << 22 | SPECIAL[a[1].lower()]
        if mnem == "jpc":
            return 3 << 30 | 5 << 27 | 3
        if mnem == "jpcrs":
            return 3 << 30 | 7 << 27 | 3
        if mnem == "hsc":
            return 0xCFC00000
        if mnem == "trap":
            nargs(1)
            v = ev(a[0])
            if not 0 <= v <= 255:
                raise AsmError("trap vector out of range")
            return 3 << 30 | 6 << 27 | ((~v & 0xFF) << 3) | 3
        raise AsmError("unknown mnemonic %r" % mnem)

    def image(self):
        img = bytearray(self.end - self.base)
        for addr, kind, payload, lineno in self.items:
            off = addr - self.base
            try:
                if kind == "insn":
                    w = self.encode(payload[0], payload[1], addr)
                    img[off:off + 4] = struct.pack(">I", w)
                elif kind == "word":
                    w = self.eval(payload, addr, True) & 0xFFFFFFFF
                    img[off:off + 4] = struct.pack(">I", w)
                else:
                    img[off:off + len(payload)] = payload
            except AsmError as ex:
                raise AsmError("line %d: %s" % (lineno, ex))
        return bytes(img)


def write_elf(path, base, image, entry, symbols, flags=1, machine=EM_MIPS_X,
              data=2, etype=2):
    """A minimal ET_EXEC: one PT_LOAD, .text, .symtab, .strtab, .shstrtab."""
    end = ">" if data == 2 else "<"
    shstr = b"\0.text\0.symtab\0.strtab\0.shstrtab\0"
    strtab = bytearray(b"\0")
    syms = [bytes(16)]
    for name, value in sorted(symbols.items(), key=lambda kv: kv[1]):
        off = len(strtab)
        strtab += name.encode() + b"\0"
        # st_name, st_value, st_size, st_info (GLOBAL NOTYPE), st_other, st_shndx
        syms.append(struct.pack(end + "IIIBBH", off, value, 0, 0x10, 0, 1))
    symtab = b"".join(syms)

    ehsize, phentsize, shentsize = 52, 32, 40
    text_off = 0x100
    sym_off = (text_off + len(image) + 3) & ~3
    str_off = sym_off + len(symtab)
    shstr_off = str_off + len(strtab)
    sh_off = (shstr_off + len(shstr) + 3) & ~3

    ident = b"\x7fELF" + bytes([1, data, 1, 0]) + bytes(8)
    ehdr = ident + struct.pack(end + "HHIIIIIHHHHHH", etype, machine, 1, entry,
                               ehsize, sh_off, flags, ehsize, phentsize, 1,
                               shentsize, 5, 4)
    phdr = struct.pack(end + "IIIIIIII", 1, text_off, base, base, len(image),
                       len(image), 7, 4)
    shdrs = [bytes(shentsize),
             struct.pack(end + "IIIIIIIIII", 1, 1, 6, base, text_off,
                         len(image), 0, 0, 4, 0),
             struct.pack(end + "IIIIIIIIII", 7, 2, 0, 0, sym_off, len(symtab),
                         3, 1, 4, 16),
             struct.pack(end + "IIIIIIIIII", 15, 3, 0, 0, str_off,
                         len(strtab), 0, 0, 1, 0),
             struct.pack(end + "IIIIIIIIII", 23, 3, 0, 0, shstr_off,
                         len(shstr), 0, 0, 1, 0)]
    out = bytearray(sh_off + shentsize * len(shdrs))
    out[0:len(ehdr)] = ehdr
    out[ehsize:ehsize + phentsize] = phdr
    out[text_off:text_off + len(image)] = image
    out[sym_off:sym_off + len(symtab)] = symtab
    out[str_off:str_off + len(strtab)] = strtab
    out[shstr_off:shstr_off + len(shstr)] = shstr
    out[sh_off:] = b"".join(shdrs)
    with open(path, "wb") as f:
        f.write(out)


def assemble_file(src_text, out_path, base=0x2000, **elf_kw):
    asm = Assembler(base)
    asm.parse(src_text)
    image = asm.image()
    entry = asm.labels.get("_start", base)
    write_elf(out_path, base, image, entry,
              {k: v for k, v in asm.labels.items()
               if not k.startswith("__")}, **elf_kw)
    return asm


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--base", type=lambda s: int(s, 0), default=0x2000)
    p.add_argument("--flags", type=lambda s: int(s, 0), default=1)
    args = p.parse_args(argv)
    with open(args.source) as f:
        text = f.read()
    try:
        assemble_file(text, args.output, args.base, flags=args.flags)
    except AsmError as ex:
        sys.stderr.write("%s: %s\n" % (args.source, ex))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
