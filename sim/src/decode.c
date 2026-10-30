/* MIPS-X (ES3890) instruction decoder and disassembler.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Encodings from spec §2-§6. Syntax from abi §10.
 */
#include <stdio.h>
#include <string.h>

#include "mipsx.h"

static const char *const opnames[OP_COUNT] = {
  [OP_INVALID] = ".word",
  [OP_LD] = "ld", [OP_ST] = "st", [OP_LDBU] = "ldbu", [OP_LDB] = "ldb",
  [OP_LDHU] = "ldhu", [OP_LDH] = "ldh", [OP_STB] = "stb", [OP_STH] = "sth",
  [OP_BEQ] = "beq", [OP_BNE] = "bne", [OP_BHS] = "bhs", [OP_BLO] = "blo",
  [OP_BLT] = "blt", [OP_BGE] = "bge",
  [OP_ADD] = "add", [OP_SUB] = "sub", [OP_SUBNC] = "subnc", [OP_AND] = "and",
  [OP_BIC] = "bic", [OP_NOT] = "not", [OP_OR] = "or", [OP_XOR] = "xor",
  [OP_MSTART] = "mstart", [OP_MSTEP] = "mstep", [OP_DSTEP] = "dstep",
  [OP_ROTLB] = "rotlb", [OP_ROTLCB] = "rotlcb", [OP_SH] = "sh", [OP_ASR] = "asr",
  [OP_ADDI] = "addi", [OP_JSPCI] = "jspci", [OP_MOVFRS] = "movfrs",
  [OP_MOVTOS] = "movtos", [OP_JPC] = "jpc", [OP_JPCRS] = "jpcrs",
  [OP_HSC] = "hsc", [OP_TRAP] = "trap",
};

const char *mx_opname(enum op op) {
  return (op >= 0 && op < OP_COUNT && opnames[op]) ? opnames[op] : "?";
}

static int32_t sext(uint32_t v, unsigned bits) {
  uint32_t m = 1u << (bits - 1);
  return (int32_t)((v ^ m) - m);
}

static uint32_t bit(unsigned r) { return r ? (1u << r) : 0; }

/* Shift amount field (spec §5): bits 6-4 bbb, bits 3-0 one-hot dddd.
 * Returns n = 32 - e (1..32), or 0 if dddd is not one-hot. */
static int shift_amount(uint32_t func) {
  unsigned bbb = (func >> 4) & 7, dddd = func & 0xF, d;
  switch (dddd) {
  case 1: d = 0; break;
  case 2: d = 1; break;
  case 4: d = 2; break;
  case 8: d = 3; break;
  default: return 0;
  }
  return 32 - (int)(bbb * 4 + d);
}

static void invalid(struct insn *in, const char *why) {
  in->op = OP_INVALID;
  in->flags = 0;
  in->reads = 0;
  in->wreg = -1;
  in->why = why;
}

void mx_decode(uint32_t w, struct insn *in) {
  unsigned ty = w >> 30, op = (w >> 27) & 7;
  unsigned s1 = (w >> 22) & 31, s2 = (w >> 17) & 31, d = (w >> 12) & 31;
  uint32_t func = w & 0xFFF;

  memset(in, 0, sizeof *in);
  in->word = w;
  in->wreg = -1;

  switch (ty) {
  case 2: { /* memory */
    static const enum op mops[8] = {OP_LD, OP_LDHU, OP_ST, OP_STB,
                                    OP_LDBU, OP_LDB, OP_STH, OP_LDH};
    static const unsigned msize[8] = {4, 2, 4, 1, 1, 1, 2, 2};
    in->op = mops[op];
    in->size = msize[op];
    in->src1 = s1;
    in->src2 = s2;
    in->imm = sext(w & 0x1FFFF, 17);
    if (in->op != OP_LD && in->op != OP_ST)
      in->flags |= F_ES3890;
    if (in->op == OP_ST || in->op == OP_STB || in->op == OP_STH) {
      in->flags |= F_STORE;
      in->reads = bit(s1) | bit(s2);
    } else {
      in->flags |= F_LOAD;
      in->dest = s2;
      in->wreg = s2 ? (int)s2 : -1;
      in->reads = bit(s1);
    }
    return;
  }
  case 0: { /* branch */
    static const enum op bops[8] = {OP_INVALID, OP_BEQ, OP_BHS, OP_BLT,
                                    OP_INVALID, OP_BNE, OP_BLO, OP_BGE};
    if (bops[op] == OP_INVALID) {
      invalid(in, "branch condition 000 or 100 is undefined");
      return;
    }
    in->op = bops[op];
    in->flags = F_BRANCH;
    in->src1 = s1;
    in->src2 = s2;
    in->sq = (w >> 16) & 1;
    in->imm = sext(w & 0xFFFF, 16);
    in->reads = bit(s1) | bit(s2);
    return;
  }
  case 1: { /* compute */
    in->src1 = s1;
    in->src2 = s2;
    in->dest = d;
    in->wreg = d ? (int)d : -1;
    in->reads = bit(s1) | bit(s2);
    if (op == 4) {
      switch (func) {
      case 0x019: in->op = OP_ADD; break;
      case 0x066: in->op = OP_SUB; break;
      case 0x026: in->op = OP_SUBNC; break;
      case 0x023: in->op = OP_AND; break;
      case 0x00B: in->op = OP_BIC; break;
      case 0x00F: in->op = OP_NOT; in->reads = bit(s1); break;
      case 0x03B: in->op = OP_OR; break;
      case 0x01B: in->op = OP_XOR; break;
      default: invalid(in, "undefined compute function (OP 100)"); return;
      }
    } else if (op == 0) {
      in->flags = F_MD;
      switch (func) {
      case 0x0E6: in->op = OP_MSTART; in->reads = bit(s2); break;
      case 0x099: in->op = OP_MSTEP; break;
      case 0x166: in->op = OP_DSTEP; break;
      default: invalid(in, "undefined compute function (OP 000)"); return;
      }
    } else if (op == 1) {
      if (func == 0x0C0) {
        in->op = OP_ROTLB;
      } else if (func == 0x080) {
        in->op = OP_ROTLCB;
      } else if ((func & 0xF80) == 0x200 || (func & 0xF80) == 0x100) {
        int n = shift_amount(func);
        if (!n) {
          invalid(in, "shift amount field dddd is not one-hot");
          return;
        }
        in->imm = n;
        if (func & 0x200) {
          in->op = OP_SH;
        } else {
          in->op = OP_ASR;
          in->reads = bit(s1);
        }
      } else {
        invalid(in, "undefined compute function (OP 001)");
        return;
      }
    } else {
      invalid(in, "undefined compute OP");
    }
    return;
  }
  case 3: { /* compute immediate */
    in->src1 = s1;
    in->imm = sext(w & 0x1FFFF, 17);
    switch (op) {
    case 4: /* addi */
      in->op = OP_ADDI;
      in->dest = s2;
      in->wreg = s2 ? (int)s2 : -1;
      in->reads = bit(s1);
      return;
    case 0: /* jspci */
      in->op = OP_JSPCI;
      in->flags = F_JUMP;
      in->dest = s2;
      in->wreg = s2 ? (int)s2 : -1;
      in->reads = bit(s1);
      return;
    case 3: /* movfrs */
    case 2: /* movtos */
      if (func & 0xFF8) {
        invalid(in, "movfrs/movtos with non-zero Func bits 11-3");
        return;
      }
      in->spec = func & 7;
      if (in->spec != SPEC_PSW && in->spec != SPEC_MD && in->spec != SPEC_PC) {
        invalid(in, "undefined special register number");
        return;
      }
      if (op == 3) {
        /* Dest is in the Src2 field, like addi; bits 16-12 are 0 (spec §2,
         * §6). */
        if (d) {
          invalid(in, "movfrs with non-zero bits 16-12 (Dest is bits 21-17)");
          return;
        }
        in->op = OP_MOVFRS;
        in->dest = s2;
        in->wreg = s2 ? (int)s2 : -1;
      } else {
        in->op = OP_MOVTOS;
        in->reads = bit(s1);
      }
      return;
    case 5: /* jpc */
    case 7: /* jpcrs */
      if (func != 0x003) {
        invalid(in, "jpc/jpcrs with Func other than 0x003");
        return;
      }
      in->op = op == 5 ? OP_JPC : OP_JPCRS;
      in->flags = F_JUMP;
      return;
    case 1:
      if (w != 0xCFC00000u) {
        /* Not undefined: later firmware executes these (spec §6), but
         * what they do is unknown. */
        invalid(in, "compute-immediate OP 001 other than hsc (0xCFC00000), "
                    "whose function is unknown (spec §6)");
        in->unknown = 1;
        return;
      }
      in->op = OP_HSC;
      in->flags = F_TRAPLIKE;
      return;
    case 6: /* trap */
      if ((func & 7) != 3 || (func & 0x800)) {
        invalid(in, "trap with Func bits 2-0 not 011 or bit 11 set");
        return;
      }
      in->op = OP_TRAP;
      in->flags = F_TRAPLIKE;
      in->vector = (~(func >> 3)) & 0xFF;
      return;
    }
  }
  }
  invalid(in, "undecodable");
}

static const char *specname(unsigned spec, int write) {
  switch (spec) {
  case SPEC_PSW: return "psw";
  case SPEC_MD: return "md";
  case SPEC_PC: return write ? "pcm1" : "pcm4";
  }
  return "?";
}

void mx_disasm(const struct insn *in, uint32_t pc, char *buf, size_t n) {
  const char *name = mx_opname(in->op);
  switch (in->op) {
  case OP_INVALID:
    snprintf(buf, n, ".word 0x%08x", in->word);
    return;
  case OP_LD: case OP_LDBU: case OP_LDB: case OP_LDHU: case OP_LDH:
  case OP_ST: case OP_STB: case OP_STH:
    snprintf(buf, n, "%s %d[r%u],r%u", name, in->imm, in->src1, in->src2);
    return;
  case OP_BEQ: case OP_BNE: case OP_BHS: case OP_BLO: case OP_BLT:
  case OP_BGE: {
    uint32_t target = (pc + 2 + (uint32_t)in->imm) * 4;
    if (in->op == OP_BEQ && in->src1 == 0 && in->src2 == 0)
      snprintf(buf, n, "b%s 0x%x", in->sq ? "sq" : "", target);
    else
      snprintf(buf, n, "%s%s r%u,r%u,0x%x", name, in->sq ? "sq" : "",
               in->src1, in->src2, target);
    return;
  }
  case OP_ADD:
    if (in->word == 0x60000019u)
      snprintf(buf, n, "nop");
    else if (in->src2 == 0)
      snprintf(buf, n, "mov r%u,r%u", in->src1, in->dest);
    else
      snprintf(buf, n, "add r%u,r%u,r%u", in->src1, in->src2, in->dest);
    return;
  case OP_NOT:
    snprintf(buf, n, "not r%u,r%u", in->src1, in->dest);
    return;
  case OP_MSTART:
    snprintf(buf, n, "mstart r%u,r%u", in->src2, in->dest);
    return;
  case OP_SH:
    if (in->src1 == 0)
      snprintf(buf, n, "lsl r%u,r%u,#%d", in->src2, in->dest, 32 - in->imm);
    else if (in->src2 == 0)
      snprintf(buf, n, "lsr r%u,r%u,#%d", in->src1, in->dest, in->imm);
    else
      snprintf(buf, n, "sh r%u,r%u,r%u,#%d", in->src1, in->src2, in->dest,
               in->imm);
    return;
  case OP_ASR:
    snprintf(buf, n, "asr r%u,r%u,#%d", in->src1, in->dest, in->imm);
    return;
  case OP_ADDI:
    snprintf(buf, n, "addi r%u,#%d,r%u", in->src1, in->imm, in->dest);
    return;
  case OP_JSPCI:
    if (in->src1 == 31 && in->imm == 0 && in->dest == 0)
      snprintf(buf, n, "ret");
    else
      snprintf(buf, n, "jspci r%u,#%d,r%u", in->src1, in->imm, in->dest);
    return;
  case OP_MOVFRS:
    snprintf(buf, n, "movfrs %s,r%u", specname(in->spec, 0), in->dest);
    return;
  case OP_MOVTOS:
    snprintf(buf, n, "movtos r%u,%s", in->src1, specname(in->spec, 1));
    return;
  case OP_JPC: case OP_JPCRS: case OP_HSC:
    snprintf(buf, n, "%s", name);
    return;
  case OP_TRAP:
    snprintf(buf, n, "trap #%u", in->vector);
    return;
  default:
    snprintf(buf, n, "%s r%u,r%u,r%u", name, in->src1, in->src2, in->dest);
    return;
  }
}
