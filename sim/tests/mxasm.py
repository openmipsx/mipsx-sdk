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
# %call() is accepted in a jspci immediate and means %w() (an absolute
# word address through r0, what R_MIPSX_CALL17 picks below 256 KB).
#
# Sections and linking (for the run-time tests in rt/, work package S7):
#   .text .data .bss .rodata and '.section NAME[,flags...]' switch output
#   section (input names map to the output sections of rt/sim.ld, so
#   .text.start goes to .text).  .set/.equ NAME,EXPR define symbols;
#   .p2align/.balign align; .globl .global .weak .type .size .file are
#   accepted and ignored (every symbol is global).  '.L' labels are local
#   to their source file.  With several source files, or --link, the
#   files are laid out like rt/sim.ld (link_layout below) and the
#   linker-defined symbols of abi §13.1 are defined.  Without sections
#   everything is in .text at --base, as before.

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

# Output sections in rt/sim.ld order; .sbss and .bss hold no file data.
OUTPUT_SECTIONS = [".vectors", ".text", ".rodata", ".init_array",
                   ".fini_array", ".data", ".sdata", ".sbss", ".bss"]
NOBITS = {".sbss", ".bss"}
IGNORED_DIRECTIVES = {".globl", ".global", ".weak", ".type", ".size", ".file",
                      ".ident"}


class AsmError(Exception):
    pass


def output_section(name):
    """Maps an input section name to its output section, as rt/sim.ld."""
    if name == ".scommon":
        return ".sbss"
    for out in OUTPUT_SECTIONS:
        if name == out or name.startswith(out + "."):
            return out
    raise AsmError("section %s is not placed by the linker script" % name)


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
    def __init__(self, base=0x2000, bases=None, symbols=None):
        self.base = base
        # Start address of each output section (link mode); .text at base.
        self.bases = dict(bases or {})
        self.bases.setdefault(".text", base)
        self.sec = ".text"
        self.pcs = {}        # output section -> current address
        self.items = []      # (addr, kind, payload, lineno, section)
        self.labels = dict(symbols or {})
        self.expects = []
        self.local_count = {}

    # -- expressions ------------------------------------------------------
    def eval(self, expr, pc, final):
        """Evaluates EXPR: numbers, symbols, '.', parentheses, unary and
        binary + and -, and %hi() %lo() %w() %call()."""
        e = expr.strip()
        if e.startswith("#"):
            e = e[1:].strip()
        toks = re.findall(r"0[xX][0-9a-fA-F]+|\d+|%(?:hi|lo|w|call)\(|"
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
                elif t in ("%w(", "%call("):
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
    def parse(self, text, fileno=0):
        self.sec = ".text"
        pc = self.pcs.get(self.sec, self.bases[self.sec])
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
            # '.L' labels are local to their file
            line = re.sub(r"(?<![\w.$])\.L(?=[\w.$])", ".L%d_" % fileno, line)
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
            if mnem in IGNORED_DIRECTIVES:
                continue
            if mnem in (".text", ".data", ".bss", ".rodata", ".section"):
                name = mnem if mnem != ".section" else split_operands(ops)[0]
                try:
                    out_sec = output_section(name)
                except AsmError as ex:
                    raise AsmError("line %d: %s" % (lineno, ex))
                self.pcs[self.sec] = pc
                self.sec = out_sec
                pc = self.pcs.get(out_sec, self.bases.get(out_sec, 0))
                continue

            def local_ref(m):
                n, d = m.group(1), m.group(2)
                k = self.local_count.get(n, 0)
                return "__L%s_%d" % (n, k + 1 if d == "f" else k)
            ops = re.sub(r"(?<![\w.$])(\d+)([fb])(?![\w.$])", local_ref, ops)
            try:
                pc = self.statement(mnem, ops, pc, lineno)
            except AsmError as ex:
                raise AsmError("line %d: %s" % (lineno, ex))
        self.pcs[self.sec] = pc
        if self.expects:
            self.sec = ".text"
            pc = (self.pcs.get(".text", self.bases[".text"]) + 3) & ~3
            for (label, lineno) in self.expects:
                self.labels[label] = pc
                for m_, o_ in [("addi", "r0,#%d,r1" % (lineno & 0xFF)),
                               ("st", "%d[r0],r1" % IO_EXIT)]:
                    self.add(pc, "insn", (m_, o_), lineno)
                    pc += 4
            self.pcs[".text"] = pc
            self.expects = []
        self.end = self.pcs.get(".text", self.bases[".text"])

    def add(self, pc, kind, payload, lineno):
        if self.sec in NOBITS and not (kind == "bytes" and not any(payload)):
            raise AsmError("data in %s" % self.sec)
        self.items.append((pc, kind, payload, lineno, self.sec))

    def sizes(self):
        """Size in bytes of each output section used."""
        return {sec: pc - self.bases.get(sec, 0) for sec, pc in self.pcs.items()}

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
                self.add(pc, "word", "0", lineno)
                pc += 4
            return pc
        if mnem == ".word":
            for e in split_operands(ops):
                self.add(pc, "word", e, lineno)
                pc += 4
            return pc
        if mnem == ".space":
            n = self.eval(ops, pc, True)
            self.add(pc, "bytes", bytes(n), lineno)
            return pc + n
        if mnem in (".set", ".equ"):
            a = split_operands(ops)
            self.labels[a[0]] = self.eval(a[1], pc, False)
            return pc
        if mnem in (".align", ".p2align", ".balign"):
            v = self.eval(split_operands(ops)[0], pc, True)
            a = v if mnem == ".balign" else 1 << v
            n = (-pc) % a
            if n:
                self.add(pc, "bytes", bytes(n), lineno)
            return pc + n
        if mnem in (".ascii", ".asciz"):
            m = re.fullmatch(r'"(.*)"', ops.strip())
            if not m:
                raise AsmError("bad string")
            data = m.group(1).encode().decode("unicode_escape").encode("latin-1")
            if mnem == ".asciz":
                data += b"\0"
            self.add(pc, "bytes", data, lineno)
            return pc + len(data)
        if pc & 3:
            raise AsmError("instruction at unaligned address 0x%x" % pc)
        # pseudo-instructions that expand to several words
        if mnem == "li":
            a = split_operands(ops)
            for m_, o_ in self.li_seq(a[0], reg(a[1]), pc):
                self.add(pc, "insn", (m_, o_), lineno)
                pc += 4
            return pc
        if mnem == "la":
            a = split_operands(ops)
            rd = reg(a[1])
            for m_, o_ in [("addi", "r0,#%%hi(%s),r%d" % (a[0], rd)),
                           ("lsl", "r%d,r%d,#15" % (rd, rd)),
                           ("addi", "r%d,#%%lo(%s),r%d" % (rd, a[0], rd))]:
                self.add(pc, "insn", (m_, o_), lineno)
                pc += 4
            return pc
        if mnem == "expect":
            a = split_operands(ops)
            label = "__expect_fail_%d" % len(self.expects)
            self.expects.append((label, lineno))
            seq = self.li_seq(a[1], 1, pc) + [("bne", "%s,r1,%s" % (a[0], label)),
                                        ("nop", ""), ("nop", "")]
            for m_, o_ in seq:
                self.add(pc, "insn", (m_, o_), lineno)
                pc += 4
            return pc
        if mnem == "exit":
            value = self.eval(ops, pc, True)
            for m_, o_ in li_words(value, 1) + [("st", "%d[r0],r1" % IO_EXIT)]:
                self.add(pc, "insn", (m_, o_), lineno)
                pc += 4
            return pc
        self.add(pc, "insn", (mnem, ops), lineno)
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
            return 3 << 30 | 3 << 27 | reg(a[1]) << 17 | SPECIAL[a[0].lower()]
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

    def image(self, sec=".text"):
        start = self.bases.get(sec, 0)
        img = bytearray(self.pcs.get(sec, start) - start)
        for addr, kind, payload, lineno, isec in self.items:
            if isec != sec:
                continue
            off = addr - start
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


def write_elf_sections(path, sections, entry, symbols, flags=1,
                       machine=EM_MIPS_X, data=2, etype=2):
    """Writes an ET_EXEC with one PT_LOAD per section.  SECTIONS is a list
    of (name, vaddr, paddr, contents, size); contents is None for a NOBITS
    section.  Also .symtab, .strtab and .shstrtab."""
    end = ">" if data == 2 else "<"
    ehsize, phentsize, shentsize = 52, 32, 40
    shstr = bytearray(b"\0")

    def shname(n):
        off = len(shstr)
        shstr.extend(n.encode() + b"\0")
        return off

    sec_names = [shname(s[0]) for s in sections]
    n_symtab, n_strtab, n_shstr = shname(".symtab"), shname(".strtab"), \
        shname(".shstrtab")

    def shndx(value):
        for i, (_, vaddr, _, _, size) in enumerate(sections):
            if vaddr <= value < vaddr + size or (size == 0 and value == vaddr):
                return i + 1
        return 0xFFF1  # SHN_ABS

    strtab = bytearray(b"\0")
    syms = [bytes(16)]
    for name, value in sorted(symbols.items(), key=lambda kv: (kv[1], kv[0])):
        off = len(strtab)
        strtab += name.encode() + b"\0"
        # st_name, st_value, st_size, st_info (GLOBAL NOTYPE), st_other, st_shndx
        syms.append(struct.pack(end + "IIIBBH", off, value & 0xFFFFFFFF, 0,
                                0x10, 0, shndx(value)))
    symtab = b"".join(syms)

    loads = [s for s in sections if s[4]]
    pos = ehsize + phentsize * len(loads)
    pos = (pos + 0xFF) & ~0xFF
    offsets = []
    for name, vaddr, paddr, contents, size in sections:
        pos = (pos + 3) & ~3
        offsets.append(pos)
        if contents is not None:
            pos += len(contents)
    sym_off = (pos + 3) & ~3
    str_off = sym_off + len(symtab)
    shstr_off = str_off + len(strtab)
    sh_off = (shstr_off + len(shstr) + 3) & ~3
    nsh = len(sections) + 4

    ident = b"\x7fELF" + bytes([1, data, 1, 0]) + bytes(8)
    ehdr = ident + struct.pack(end + "HHIIIIIHHHHHH", etype, machine, 1, entry,
                               ehsize, sh_off, flags, ehsize, phentsize,
                               len(loads), shentsize, nsh, nsh - 1)
    phdrs, shdrs = [], [bytes(shentsize)]
    for i, (name, vaddr, paddr, contents, size) in enumerate(sections):
        filesz = len(contents) if contents is not None else 0
        pflags = 5 if name in (".text", ".vectors") else 6
        if size:
            phdrs.append(struct.pack(end + "IIIIIIII", 1, offsets[i], vaddr,
                                     paddr, filesz, size, pflags, 4))
        shflags = 6 if pflags == 5 else 3
        shdrs.append(struct.pack(end + "IIIIIIIIII", sec_names[i],
                                 1 if contents is not None else 8, shflags,
                                 vaddr, offsets[i], size, 0, 0, 4, 0))
    shdrs += [struct.pack(end + "IIIIIIIIII", n_symtab, 2, 0, 0, sym_off,
                          len(symtab), len(sections) + 2, 1, 4, 16),
              struct.pack(end + "IIIIIIIIII", n_strtab, 3, 0, 0, str_off,
                          len(strtab), 0, 0, 1, 0),
              struct.pack(end + "IIIIIIIIII", n_shstr, 3, 0, 0, shstr_off,
                          len(shstr), 0, 0, 1, 0)]
    out = bytearray(sh_off + shentsize * nsh)
    out[0:len(ehdr)] = ehdr
    ph = b"".join(phdrs)
    out[ehsize:ehsize + len(ph)] = ph
    for i, s in enumerate(sections):
        if s[3] is not None:
            out[offsets[i]:offsets[i] + len(s[3])] = s[3]
    out[sym_off:sym_off + len(symtab)] = symtab
    out[str_off:str_off + len(strtab)] = strtab
    out[shstr_off:shstr_off + len(shstr)] = shstr
    out[sh_off:] = b"".join(shdrs)
    with open(path, "wb") as f:
        f.write(out)


def write_elf(path, base, image, entry, symbols, flags=1, machine=EM_MIPS_X,
              data=2, etype=2):
    """A minimal ET_EXEC: one PT_LOAD for .text at BASE."""
    write_elf_sections(path, [(".text", base, base, image, len(image))],
                       entry, symbols, flags, machine, data, etype)


def assemble_file(src_text, out_path, base=0x2000, **elf_kw):
    asm = Assembler(base)
    asm.parse(src_text)
    image = asm.image()
    entry = asm.labels.get("_start", base)
    write_elf(out_path, base, image, entry,
              {k: v for k, v in asm.labels.items()
               if not k.startswith("__")}, **elf_kw)
    return asm


def align(v, a):
    return (v + a - 1) & -a


def link_layout(sizes, text_base=0x2000, data_vma=None, ram_size=0x200000):
    """Places output sections and defines the abi §13.1 symbols the way
    rt/sim.ld (and rt/device.ld) do.  Returns ({section: (vma, lma)},
    symbols).  DATA_VMA, if given, moves .data/.sdata to that run address
    while their load address stays after .fini_array, as an 'AT>' clause
    would; the tests use it to check crt0's .data copy."""
    place, sym = {}, {}
    sz = lambda s: align(sizes.get(s, 0), 4)
    if sizes.get(".vectors"):
        place[".vectors"] = (0, 0)
    pc = text_base
    place[".text"] = (pc, pc)
    sym["__text_start"] = pc
    pc += sz(".text")
    sym["__text_end"] = pc
    pc = align(pc, 8)
    place[".rodata"] = (pc, pc)
    pc = align(pc + sz(".rodata"), 4)
    place[".init_array"] = (pc, pc)
    sym["__init_array_start"] = pc
    pc += sz(".init_array")
    sym["__init_array_end"] = pc
    pc = align(pc, 4)
    place[".fini_array"] = (pc, pc)
    sym["__fini_array_start"] = pc
    pc += sz(".fini_array")
    sym["__fini_array_end"] = pc
    lma = align(pc, 8)
    vma = lma if data_vma is None else data_vma
    place[".data"] = (vma, lma)
    sym["__data_start"] = vma
    sym["__data_load"] = lma
    vma += sz(".data")
    lma += sz(".data")
    place[".sdata"] = (vma, lma)
    sym["__sdata_start"] = vma
    vma += sz(".sdata")
    sym["__data_end"] = vma
    vma = align(vma, 8)
    place[".sbss"] = (vma, vma)
    sym["__bss_start"] = vma
    vma += sz(".sbss")
    place[".bss"] = (vma, vma)
    vma = align(vma + sz(".bss"), 8)
    sym["__bss_end"] = vma
    sym["_end"] = max(vma, align(lma, 8))
    sym["__mipsx_cb0"] = sym["__text_start"] + 0x40000
    sym["__mipsx_cb1"] = sym["__mipsx_cb0"] + 0x80000
    sym["_gp"] = (sym["__sdata_start"] if sizes.get(".sdata")
                  else sym["__data_start"]) + 0x10000
    sym["__stack_top"] = ram_size - 16
    sym["__heap_start"] = sym["_end"]
    sym["__heap_end"] = sym["__stack_top"] - 0x10000
    return place, sym


def link(sources, out_path, text_base=0x2000, data_vma=None, bss_fill=None,
         flags=1, names=None):
    """Assembles SOURCES (a list of source texts) as one program laid out by
    link_layout, and writes the ELF.  BSS_FILL, a byte value, makes the
    ELF load that value over .sbss/.bss (as PROGBITS), so that tests can
    see crt0 clear them."""
    bases, syms = {}, {}
    for _ in range(10):
        asm = Assembler(text_base, bases, syms)
        for i, text in enumerate(sources):
            try:
                asm.parse(text, i)
            except AsmError as ex:
                raise AsmError("%s: %s" % (names[i] if names else
                                           "source %d" % (i + 1), ex))
        place, new_syms = link_layout(asm.sizes(), text_base, data_vma)
        new_bases = {s: v for s, (v, _) in place.items()}
        if new_bases == bases and new_syms == syms:
            break
        bases, syms = new_bases, new_syms
    else:
        raise AsmError("layout did not converge")
    sizes = asm.sizes()
    sections = []
    for sec in OUTPUT_SECTIONS:
        if sec not in place or (sec not in sizes and sec != ".text"):
            continue
        vma, lma = place[sec]
        size = sizes.get(sec, 0)
        if sec in NOBITS:
            contents = None if bss_fill is None else bytes([bss_fill]) * size
        else:
            contents = asm.image(sec)
        sections.append((sec, vma, lma, contents, size))
    if "_start" not in asm.labels:
        raise AsmError("no _start")
    symbols = {k: v for k, v in asm.labels.items()
               if not k.startswith("__L") and not k.startswith("__expect")}
    write_elf_sections(out_path, sections, asm.labels["_start"], symbols,
                       flags)
    return asm


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sources", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--base", type=lambda s: int(s, 0), default=0x2000)
    p.add_argument("--flags", type=lambda s: int(s, 0), default=1)
    p.add_argument("--link", action="store_true",
                   help="lay out sections like rt/sim.ld (implied by "
                   "several sources)")
    p.add_argument("--data-vma", type=lambda s: int(s, 0),
                   help="with --link: run address of .data (load address "
                   "stays after .fini_array)")
    p.add_argument("--bss-fill", type=lambda s: int(s, 0),
                   help="with --link: load this byte over .bss")
    args = p.parse_args(argv)
    texts = []
    for path in args.sources:
        with open(path) as f:
            texts.append(f.read())
    try:
        if args.link or len(texts) > 1:
            link(texts, args.output, args.base, args.data_vma, args.bss_fill,
                 args.flags, args.sources)
        else:
            try:
                assemble_file(texts[0], args.output, args.base,
                              flags=args.flags)
            except AsmError as ex:
                raise AsmError("%s: %s" % (args.sources[0], ex))
    except AsmError as ex:
        sys.stderr.write("mxasm: %s\n" % ex)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
