/* MIPS-X (ES3890) instruction-set simulator.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Models the programmer-visible pipeline: two delay slots after every
 * branch and jump, squashing branches, the load delay slot, MD and the
 * step instructions, the PC chain, and the PSW as far as the manual
 * describes it.  Pipeline rule violations (abi §9) are reported, by
 * default as errors.  See sim/README.md.
 */
#include <getopt.h>
#include <inttypes.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mipsx.h"

#define SIM_VERSION "0.1"

/* Exit statuses of the simulator itself. */
#define EXIT_CYCLE_LIMIT 124
#define EXIT_SIM_ERROR 125
#define EXIT_LOAD_ERROR 126

enum hazmode { HAZ_ERROR, HAZ_WARN, HAZ_OFF };

#define DCACHE_SIZE 16384

struct dcache {
  struct insn in;
  int valid;
};

struct cpu {
  uint32_t r[32];
  uint32_t md, psw;
  uint32_t chain[3]; /* PC chain; chain[0] is the PC-4 (read) end */

  /* Fetch queue of word addresses: q[0] executes now, q[1] and q[2] are
   * already in the pipeline.  Per entry: squashed, and which delay slot
   * (1 or 2, 0 = none) of which control transfer it occupies. */
  uint32_t q[3];
  uint8_t sqd[3];
  uint8_t slot[3];
  uint32_t owner[3];
  enum op owner_op[3];

  uint8_t *mem;
  uint32_t memsize;
  int es3890;

  uint64_t cycles, instret, squashed, stalls, slots, slot_nops;
  uint64_t max_cycles;
  uint64_t warnings;
  uint32_t cyc_hi_latch, ins_hi_latch;

  /* Hazard tracking: state left by the previous pipeline slot. */
  int load_reg;      /* destination of a load in the previous slot, or 0 */
  uint32_t load_pc;
  int md_prev;       /* 1 = movtos md, 2 = mstart/mstep/dstep */
  uint32_t md_prev_pc;
  int prev_store;
  uint32_t prev_pc;

  enum hazmode hz;
  struct dcache dc[DCACHE_SIZE];
  FILE *trace;
  struct program prog;
  int exited;
  int exit_code;
  jmp_buf stop;
  int stop_status;
};

static uint32_t bitr(unsigned r) { return r ? (1u << r) : 0; }

static void where(const struct cpu *c, uint32_t pcw, char *buf, size_t n) {
  uint32_t addr = pcw * 4;
  const struct symbol *s = elf_symbolize(&c->prog, addr);
  if (s && addr == s->addr)
    snprintf(buf, n, "pc 0x%08x <%s>", addr, s->name);
  else if (s && addr - s->addr < 0x100000)
    snprintf(buf, n, "pc 0x%08x <%s+0x%x>", addr, s->name, addr - s->addr);
  else
    snprintf(buf, n, "pc 0x%08x", addr);
}

__attribute__((noreturn)) static void halt(struct cpu *c, int status) {
  c->stop_status = status;
  longjmp(c->stop, 1);
}

static void vreport(struct cpu *c, const char *kind, uint32_t pcw,
                    const char *fmt, va_list ap) {
  char loc[160];
  fflush(stdout);
  where(c, pcw, loc, sizeof loc);
  fprintf(stderr, "mipsx-sim: %s: %s: ", kind, loc);
  vfprintf(stderr, fmt, ap);
  fprintf(stderr, " (cycle %" PRIu64 ")\n", c->cycles);
}

/* A fatal simulation error: always stops. */
__attribute__((noreturn, format(printf, 3, 4)))
static void sim_error(struct cpu *c, uint32_t pcw, const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vreport(c, "error", pcw, fmt, ap);
  va_end(ap);
  halt(c, EXIT_SIM_ERROR);
}

/* A pipeline rule violation (abi §9): an error, a warning or nothing. */
__attribute__((format(printf, 3, 4)))
static void hazard(struct cpu *c, uint32_t pcw, const char *fmt, ...) {
  va_list ap;
  if (c->hz == HAZ_OFF)
    return;
  c->warnings++;
  if (c->hz == HAZ_WARN && c->warnings > 100) {
    if (c->warnings == 101)
      fprintf(stderr, "mipsx-sim: warning: too many hazard warnings; "
                      "further ones are not shown\n");
    return;
  }
  va_start(ap, fmt);
  vreport(c, c->hz == HAZ_ERROR ? "error" : "warning", pcw, fmt, ap);
  va_end(ap);
  if (c->hz == HAZ_ERROR)
    halt(c, EXIT_SIM_ERROR);
}

static const char *disas(uint32_t pcw, const struct insn *in, char *buf,
                         size_t n) {
  mx_disasm(in, pcw, buf, n);
  return buf;
}

/* ---- Memory ------------------------------------------------------------ */

static int is_io(uint32_t addr) { return addr - IO_BASE < IO_SIZE; }

static uint32_t io_load(struct cpu *c, uint32_t off, unsigned size,
                        uint32_t pcw) {
  if (size != 4)
    sim_error(c, pcw, "I/O page register at offset 0x%02x must be read "
              "with a word load", off);
  switch (off) {
  case IO_CYCLE_LO:
    c->cyc_hi_latch = (uint32_t)(c->cycles >> 32);
    return (uint32_t)c->cycles;
  case IO_CYCLE_HI:
    return c->cyc_hi_latch;
  case IO_INSTRET_LO:
    c->ins_hi_latch = (uint32_t)(c->instret >> 32);
    return (uint32_t)c->instret;
  case IO_INSTRET_HI:
    return c->ins_hi_latch;
  case IO_GETCHAR: {
    fflush(stdout);
    int ch = getchar();
    return ch == EOF ? 0xFFFFFFFFu : (uint32_t)ch;
  }
  }
  sim_error(c, pcw, "load from undefined I/O page address 0x%08x",
            IO_BASE + off);
  return 0;
}

static void io_store(struct cpu *c, uint32_t off, unsigned size, uint32_t v,
                     uint32_t pcw) {
  switch (off) {
  case IO_PUTCHAR:
    putchar((int)(v & 0xFF));
    return;
  case IO_PUTCHAR_ERR:
    fflush(stdout);
    fputc((int)(v & 0xFF), stderr);
    return;
  case IO_EXIT:
    if (size != 4)
      sim_error(c, pcw, "exit register must be written with a word store");
    c->exited = 1;
    c->exit_code = (int)v;
    return;
  }
  sim_error(c, pcw, "store to undefined I/O page address 0x%08x",
            IO_BASE + off);
}

static uint32_t check_addr(struct cpu *c, uint32_t addr, unsigned size,
                           uint32_t pcw, const struct insn *in) {
  if (addr & (size - 1)) {
    char d[64];
    hazard(c, pcw, "misaligned %u-byte access to 0x%08x (P5): %s", size, addr,
           disas(pcw, in, d, sizeof d));
    addr &= ~(uint32_t)(size - 1); /* the hardware drops the low bits */
  }
  return addr;
}

static uint32_t mem_load(struct cpu *c, uint32_t addr, const struct insn *in,
                         uint32_t pcw) {
  unsigned size = in->size;
  addr = check_addr(c, addr, size, pcw, in);
  if (is_io(addr))
    return io_load(c, addr - IO_BASE, size, pcw);
  if (addr >= c->memsize || c->memsize - addr < size)
    sim_error(c, pcw, "load from unmapped address 0x%08x", addr);
  const uint8_t *p = c->mem + addr;
  uint32_t v;
  switch (in->op) {
  case OP_LD:
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 |
           p[3];
  case OP_LDBU: return p[0];
  case OP_LDB: return (uint32_t)(int32_t)(int8_t)p[0];
  case OP_LDHU: return (uint32_t)p[0] << 8 | p[1];
  case OP_LDH:
    v = (uint32_t)p[0] << 8 | p[1];
    return (uint32_t)(int32_t)(int16_t)v;
  default: return 0;
  }
}

static void mem_store(struct cpu *c, uint32_t addr, uint32_t v,
                      const struct insn *in, uint32_t pcw) {
  unsigned size = in->size;
  addr = check_addr(c, addr, size, pcw, in);
  if (is_io(addr)) {
    io_store(c, addr - IO_BASE, size, v, pcw);
    return;
  }
  if (addr >= c->memsize || c->memsize - addr < size)
    sim_error(c, pcw, "store to unmapped address 0x%08x", addr);
  uint8_t *p = c->mem + addr;
  switch (size) {
  case 4:
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
    break;
  case 2:
    p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v;
    break;
  default:
    p[0] = (uint8_t)v;
    break;
  }
}

static int fetch(struct cpu *c, uint32_t pcw, uint32_t *word) {
  if (pcw >= c->memsize / 4)
    return 0;
  const uint8_t *p = c->mem + pcw * 4;
  *word = (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 |
          p[3];
  return 1;
}

/* ---- PSW and PC chain --------------------------------------------------- */

/* PSWother <- PSWcurrent (on a trap). */
static uint32_t psw_save(uint32_t psw) {
  uint32_t cur_low = psw & (PSW_S | PSW_I | PSW_M | PSW_V); /* -> << 1 */
  uint32_t cur_high = psw & (PSW_O | PSW_U);                /* -> >> 1 */
  uint32_t keep = psw & ~(PSW_s | PSW_i | PSW_m | PSW_v | PSW_o | PSW_u);
  return keep | cur_low << 1 | cur_high >> 1;
}

/* PSWcurrent <- PSWother (jpcrs). */
static uint32_t psw_restore(uint32_t psw) {
  uint32_t oth_low = psw & (PSW_s | PSW_i | PSW_m | PSW_v);
  uint32_t oth_high = psw & (PSW_o | PSW_u);
  uint32_t keep = psw & ~PSW_CUR_MASK;
  return keep | oth_low >> 1 | oth_high << 1;
}

static uint32_t chain_rotate(struct cpu *c) {
  uint32_t t = c->chain[0];
  if (c->psw & PSW_S) {
    c->chain[0] = c->chain[1];
    c->chain[1] = c->chain[2];
    c->chain[2] = t;
  }
  return t;
}

/* ---- Execution ---------------------------------------------------------- */

#define TRACE_EFFECT_LEN 96

/* Not inlined: main() calls setjmp, which would pessimise it. */
__attribute__((noinline)) static void step(struct cpu *c) {
  uint32_t pcw = c->q[0];
  int squashed = c->sqd[0];
  int slot = c->slot[0];
  enum op owner_op = c->owner_op[0];
  uint32_t word = 0;
  const struct insn *in;
  char d[64], eff[TRACE_EFFECT_LEN];
  eff[0] = 0;

  if (c->max_cycles && c->cycles >= c->max_cycles) {
    char loc[160];
    fflush(stdout);
    where(c, pcw, loc, sizeof loc);
    fprintf(stderr, "mipsx-sim: error: cycle limit of %" PRIu64
            " reached at %s\n", c->max_cycles, loc);
    halt(c, EXIT_CYCLE_LIMIT);
  }

  int have = fetch(c, pcw, &word);
  if (!have && !squashed) {
    if (is_io(pcw * 4) && pcw < 0x40000000u)
      sim_error(c, pcw, "instruction fetch from the I/O page");
    sim_error(c, pcw, "instruction fetch from unmapped address 0x%08x",
              pcw * 4);
  }
  if (!have)
    word = 0x60000019u;
  {
    /* Direct-mapped decode cache, keyed by the instruction word so that
     * stores into code are seen. */
    struct dcache *e = &c->dc[pcw & (DCACHE_SIZE - 1)];
    if (!e->valid || e->in.word != word) {
      mx_decode(word, &e->in);
      e->valid = 1;
    }
    in = &e->in;
  }

  /* Static delay-slot rules (P3, §9.2).  The slots of jpc and jpcrs hold
   * the restarted instructions of an exception return (manual App. VI),
   * which may be anything, so they are exempt. */
  if (slot && have && owner_op != OP_JPC && owner_op != OP_JPCRS &&
      ((in->flags & F_CTL) || (slot == 2 && (in->flags & F_LOAD)))) {
    char o[160];
    where(c, c->owner[0], o, sizeof o);
    if (in->flags & F_CTL)
      hazard(c, pcw, "%s in delay slot %d of the %s at %s (P3)",
             disas(pcw, in, d, sizeof d), slot, mx_opname(owner_op), o + 3);
    if (slot == 2 && (in->flags & F_LOAD))
      hazard(c, pcw, "load in the second delay slot of the %s at %s "
             "(abi §9.2): %s", mx_opname(owner_op), o + 3,
             disas(pcw, in, d, sizeof d));
  }
  if (slot) {
    c->slots++;
    if (have && word == 0x60000019u)
      c->slot_nops++;
  }

  /* Shift the fetch queue; the new entry defaults to sequential. */
  uint32_t q1 = c->q[1];
  uint32_t next = c->q[2] + 1;
  c->q[0] = c->q[1]; c->sqd[0] = c->sqd[1]; c->slot[0] = c->slot[1];
  c->owner[0] = c->owner[1]; c->owner_op[0] = c->owner_op[1];
  c->q[1] = c->q[2]; c->sqd[1] = c->sqd[2]; c->slot[1] = c->slot[2];
  c->owner[1] = c->owner[2]; c->owner_op[1] = c->owner_op[2];
  c->sqd[2] = 0; c->slot[2] = 0;

  c->cycles++;
  if (squashed) {
    c->squashed++;
    c->load_reg = 0;
    c->md_prev = 0;
    c->prev_store = 0;
    c->prev_pc = pcw;
    c->q[2] = next;
    if (c->trace)
      fprintf(c->trace, "%10" PRIu64 " %08x: %08x  %-30s ; squashed\n",
              c->cycles - 1, pcw * 4, have ? word : 0,
              have ? disas(pcw, in, d, sizeof d) : "?");
    return;
  }

  if (in->op == OP_INVALID)
    sim_error(c, pcw, "undefined instruction 0x%08x: %s", word, in->why);
  if ((in->flags & F_ES3890) && !c->es3890)
    sim_error(c, pcw, "%s is an ES3890 instruction, but the program's "
              "e_flags lack EF_MIPSX_ES3890", mx_opname(in->op));

  /* Dynamic hazards. */
  if (c->load_reg && (in->reads & bitr((unsigned)c->load_reg))) {
    char lp[160];
    where(c, c->load_pc, lp, sizeof lp);
    hazard(c, pcw, "load-use hazard (P1): %s reads r%d, loaded by the "
           "previous instruction at %s", disas(pcw, in, d, sizeof d),
           c->load_reg, lp + 3);
  }
  if (c->md_prev == 1 &&
      ((in->flags & F_MD) || (in->op == OP_MOVFRS && in->spec == SPEC_MD)))
    hazard(c, pcw, "MD hazard (P4): %s right after movtos to md",
           disas(pcw, in, d, sizeof d));
  if (c->md_prev == 2 && (in->op == OP_MOVFRS || in->op == OP_MOVTOS) &&
      in->spec == SPEC_MD)
    hazard(c, pcw, "MD hazard (P4): %s right after a multiply or divide "
           "step", disas(pcw, in, d, sizeof d));
  if ((in->flags & F_LOAD) && in->dest && in->dest == in->src1)
    hazard(c, pcw, "load overwrites its own address register r%u (P2): %s",
           in->dest, disas(pcw, in, d, sizeof d));
  if (c->prev_store && (in->flags & F_MEM)) {
    c->stalls++; /* P6: performance only */
    c->cycles++;
  }

  uint32_t *r = c->r;
  uint32_t a = r[in->src1], b = r[in->src2];
  uint32_t res = 0;
  int write = in->wreg;
  int new_load_reg = 0, new_md_prev = 0;
  int ctl = 0;            /* this instruction owns two delay slots */
  int redirect = 0;       /* the new queue entry is a jump target */
  uint32_t target = 0;

  switch (in->op) {
  case OP_LD: case OP_LDBU: case OP_LDB: case OP_LDHU: case OP_LDH: {
    uint32_t addr = a + (uint32_t)in->imm;
    res = mem_load(c, addr, in, pcw);
    new_load_reg = write > 0 ? write : 0;
    if (c->trace)
      snprintf(eff, sizeof eff, "[0x%08x]", addr);
    break;
  }
  case OP_ST: case OP_STB: case OP_STH: {
    uint32_t addr = a + (uint32_t)in->imm;
    mem_store(c, addr, b, in, pcw);
    if (c->trace) {
      uint32_t m = in->size == 4 ? 0xFFFFFFFFu : (1u << (in->size * 8)) - 1;
      snprintf(eff, sizeof eff, "[0x%08x] = 0x%0*x", addr, in->size * 2,
               b & m);
    }
    break;
  }
  case OP_BEQ: case OP_BNE: case OP_BHS: case OP_BLO: case OP_BLT:
  case OP_BGE: {
    int taken;
    switch (in->op) {
    case OP_BEQ: taken = a == b; break;
    case OP_BNE: taken = a != b; break;
    case OP_BHS: taken = a >= b; break;
    case OP_BLO: taken = a < b; break;
    case OP_BLT: taken = (int32_t)a < (int32_t)b; break;
    default: taken = (int32_t)a >= (int32_t)b; break;
    }
    ctl = 1;
    if (taken) {
      redirect = 1;
      target = pcw + 2 + (uint32_t)in->imm;
    } else if (in->sq) {
      c->sqd[0] = c->sqd[1] = 1;
    }
    if (c->trace)
      snprintf(eff, sizeof eff, taken ? "taken" :
               in->sq ? "not taken, slots squashed" : "not taken");
    break;
  }
  case OP_ADD: res = a + b; break;
  case OP_SUB: res = a - b; break;
  case OP_SUBNC: res = a + ~b; break;
  case OP_AND: res = a & b; break;
  case OP_BIC: res = b & ~a; break;
  case OP_NOT: res = ~a; break;
  case OP_OR: res = a | b; break;
  case OP_XOR: res = a ^ b; break;
  case OP_MSTART:
    res = (c->md & 0x80000000u) ? 0 - b : 0;
    c->md <<= 1;
    new_md_prev = 2;
    break;
  case OP_MSTEP:
    res = (c->md & 0x80000000u) ? (a << 1) + b : a << 1;
    c->md <<= 1;
    new_md_prev = 2;
    break;
  case OP_DSTEP: {
    uint32_t x = (a << 1) | (c->md >> 31);
    uint32_t o = x - b;
    if (o & 0x80000000u) {
      res = x;
      c->md <<= 1;
    } else {
      res = o;
      c->md = (c->md << 1) | 1;
    }
    new_md_prev = 2;
    break;
  }
  case OP_ROTLB:
  case OP_ROTLCB: {
    unsigned k = (in->op == OP_ROTLB ? b : ~b) & 3;
    res = k ? (a << (8 * k)) | (a >> (32 - 8 * k)) : a;
    break;
  }
  case OP_SH: {
    uint64_t pair = (uint64_t)b << 32 | a;
    res = (uint32_t)(pair >> in->imm);
    break;
  }
  case OP_ASR:
    res = in->imm >= 32 ? (uint32_t)((int32_t)a >> 31)
                       : (uint32_t)((int32_t)a >> in->imm);
    break;
  case OP_ADDI: res = a + (uint32_t)in->imm; break;
  case OP_JSPCI:
    ctl = 1;
    redirect = 1;
    target = a + (uint32_t)in->imm;
    res = pcw + 3;
    break;
  case OP_MOVFRS:
    switch (in->spec) {
    case SPEC_PSW: res = c->psw; break;
    case SPEC_MD:
      res = c->md;
      new_md_prev = 0;
      break;
    default:
      res = c->chain[0];
      c->chain[0] = c->chain[1];
      c->chain[1] = c->chain[2];
      c->chain[2] = 0;
      break;
    }
    break;
  case OP_MOVTOS:
    switch (in->spec) {
    case SPEC_PSW:
      if (!(c->psw & PSW_U))
        c->psw = (a & ~PSW_READONLY) | (c->psw & PSW_READONLY);
      if (c->trace)
        snprintf(eff, sizeof eff, "psw = 0x%08x", c->psw);
      break;
    case SPEC_MD:
      c->md = a;
      new_md_prev = 1;
      if (c->trace)
        snprintf(eff, sizeof eff, "md = 0x%08x", c->md);
      break;
    default:
      c->chain[0] = c->chain[1];
      c->chain[1] = c->chain[2];
      c->chain[2] = a;
      break;
    }
    break;
  case OP_JPCRS:
    if (!(c->psw & PSW_U))
      c->psw = psw_restore(c->psw) | PSW_S;
    /* fall through */
  case OP_JPC:
    ctl = 1;
    redirect = 1;
    target = chain_rotate(c);
    break;
  case OP_TRAP:
    c->chain[0] = c->prev_pc;
    c->chain[1] = pcw;
    c->chain[2] = q1;
    c->psw = psw_save(c->psw);
    c->psw = (c->psw & ~(PSW_S | PSW_U | PSW_O)) | PSW_M | PSW_V | PSW_I;
    /* The two instructions behind the trap are killed (the first one is
     * restarted by the handler's return sequence). */
    c->sqd[0] = c->sqd[1] = 1;
    c->slot[0] = c->slot[1] = 0;
    redirect = 1;
    target = in->vector * 8;
    if (c->trace)
      snprintf(eff, sizeof eff, "-> vector %u", in->vector);
    break;
  case OP_HSC:
    r[31] = pcw;
    sim_error(c, pcw, "hsc executed: processor halted");
    break;
  default:
    sim_error(c, pcw, "internal error: unhandled instruction");
  }

  if ((in->flags & F_MD) && c->trace)
    snprintf(eff + strlen(eff), sizeof eff - strlen(eff), "md = 0x%08x ",
             c->md);
  if (write > 0) {
    r[write] = res;
    if (c->trace)
      snprintf(eff + strlen(eff), sizeof eff - strlen(eff), "%sr%d = 0x%08x",
               eff[0] ? " " : "", write, res);
  }
  if (ctl) {
    /* The two entries now at q[0] and q[1] are this instruction's slots. */
    c->slot[0] = 1;
    c->slot[1] = 2;
    c->owner[0] = c->owner[1] = pcw;
    c->owner_op[0] = c->owner_op[1] = in->op;
  }
  if (redirect && c->trace && in->op != OP_TRAP && !(in->flags & F_BRANCH))
    snprintf(eff + strlen(eff), sizeof eff - strlen(eff), "%s-> 0x%08x",
             eff[0] ? " " : "", target * 4);
  c->q[2] = redirect ? target : next;

  c->instret++;
  c->load_reg = new_load_reg;
  c->load_pc = pcw;
  c->md_prev = new_md_prev;
  c->md_prev_pc = pcw;
  c->prev_store = (in->flags & F_STORE) != 0;
  c->prev_pc = pcw;

  if (c->trace)
    fprintf(c->trace, "%10" PRIu64 " %08x: %08x  %-30s %s%s\n",
            c->cycles - 1, pcw * 4, word, disas(pcw, in, d, sizeof d),
            eff[0] ? "; " : "", eff);
  if (c->exited)
    halt(c, c->exit_code & 0xFF);
}

/* ---- Driver ------------------------------------------------------------- */

/* Prints the disassembly of the executable segments (all segments if none
 * is marked executable). */
static void disassemble(const struct cpu *c) {
  const struct program *p = &c->prog;
  int any_exec = 0;
  for (unsigned i = 0; i < p->nsegs; i++)
    any_exec |= p->segs[i].exec;
  for (unsigned i = 0; i < p->nsegs; i++) {
    const struct segment *sg = &p->segs[i];
    if (any_exec && !sg->exec)
      continue;
    for (uint32_t a = (sg->addr + 3) & ~3u; a + 4 <= sg->addr + sg->size;
         a += 4) {
      const struct symbol *s = elf_symbolize(p, a);
      if (s && s->addr == a)
        for (const struct symbol *t = s; t >= p->syms && t->addr == a; t--)
          printf("%s:\n", t->name);
      uint32_t w = 0;
      struct insn in;
      char d[64];
      fetch((struct cpu *)c, a / 4, &w);
      mx_decode(w, &in);
      printf("%08x: %08x  %s\n", a, w, disas(a / 4, &in, d, sizeof d));
    }
  }
}

static void usage(FILE *f) {
  fprintf(f,
    "usage: mipsx-sim [options] program.elf\n"
    "\n"
    "Runs a linked MIPS-X (ES3890) ELF executable.  The exit status is the\n"
    "program's exit status (low 8 bits of the value stored to the exit\n"
    "register), or 124 if the cycle limit was reached, 125 on a simulation\n"
    "error (pipeline hazard, bad memory access, undefined instruction),\n"
    "126 if the program could not be loaded or the options are wrong.\n"
    "\n"
    "options:\n"
    "  -t, --trace             trace every instruction to stderr\n"
    "      --trace-file=FILE   trace to FILE instead\n"
    "  -c, --max-cycles=N      stop after N cycles (default 1000000000;\n"
    "                          0 = no limit)\n"
    "      --hazards=MODE      error (default), warn or off: what to do on\n"
    "                          a pipeline rule violation (abi.md §9)\n"
    "  -w, --warn-hazards      same as --hazards=warn\n"
    "  -m, --mem-size=BYTES    size of RAM at address 0 (default 0x200000)\n"
    "  -s, --stats             print cycle and instruction counts at exit\n"
    "  -d, --disassemble       print the program's code and exit\n"
    "  -h, --help              show this help\n"
    "  -V, --version           show the version\n");
}

static int parse_u64(const char *s, uint64_t *out) {
  char *end;
  unsigned long long v = strtoull(s, &end, 0);
  if (!*s || *end)
    return -1;
  *out = v;
  return 0;
}

int main(int argc, char **argv) {
  static struct cpu cpu;
  struct cpu *c = &cpu;
  uint64_t memsize = 0x200000, maxc = 1000000000ull;
  volatile int stats = 0;
  int dis = 0;
  const char *trace_file = NULL;
  int trace = 0;
  static const struct option opts[] = {
    {"trace", no_argument, 0, 't'},
    {"trace-file", required_argument, 0, 'T'},
    {"max-cycles", required_argument, 0, 'c'},
    {"hazards", required_argument, 0, 'H'},
    {"warn-hazards", no_argument, 0, 'w'},
    {"mem-size", required_argument, 0, 'm'},
    {"stats", no_argument, 0, 's'},
    {"disassemble", no_argument, 0, 'd'},
    {"help", no_argument, 0, 'h'},
    {"version", no_argument, 0, 'V'},
    {0, 0, 0, 0},
  };
  int o;
  c->hz = HAZ_ERROR;
  while ((o = getopt_long(argc, argv, "tc:wm:sdhV", opts, NULL)) != -1) {
    switch (o) {
    case 't': trace = 1; break;
    case 'T': trace_file = optarg; break;
    case 'c':
      if (parse_u64(optarg, &maxc)) {
        fprintf(stderr, "mipsx-sim: error: bad --max-cycles value\n");
        return EXIT_LOAD_ERROR;
      }
      break;
    case 'H':
      if (!strcmp(optarg, "error")) c->hz = HAZ_ERROR;
      else if (!strcmp(optarg, "warn")) c->hz = HAZ_WARN;
      else if (!strcmp(optarg, "off")) c->hz = HAZ_OFF;
      else {
        fprintf(stderr, "mipsx-sim: error: --hazards must be error, warn "
                        "or off\n");
        return EXIT_LOAD_ERROR;
      }
      break;
    case 'w': c->hz = HAZ_WARN; break;
    case 'm':
      if (parse_u64(optarg, &memsize) || memsize < 4096 ||
          memsize > 0xF0000000ull || (memsize & 3)) {
        fprintf(stderr, "mipsx-sim: error: bad --mem-size value\n");
        return EXIT_LOAD_ERROR;
      }
      break;
    case 's': stats = 1; break;
    case 'd': dis = 1; break;
    case 'h': usage(stdout); return 0;
    case 'V': printf("mipsx-sim %s\n", SIM_VERSION); return 0;
    default: usage(stderr); return EXIT_LOAD_ERROR;
    }
  }
  if (optind != argc - 1) {
    usage(stderr);
    return EXIT_LOAD_ERROR;
  }

  c->memsize = (uint32_t)memsize;
  c->mem = calloc(1, c->memsize);
  if (!c->mem) {
    fprintf(stderr, "mipsx-sim: error: out of memory\n");
    return EXIT_LOAD_ERROR;
  }
  if (elf_load(argv[optind], c->mem, c->memsize, &c->prog))
    return EXIT_LOAD_ERROR;
  if (dis) {
    disassemble(c);
    return 0;
  }
  c->es3890 = (c->prog.flags & EF_MIPSX_ES3890) != 0;
  c->max_cycles = maxc;
  if (trace_file) {
    c->trace = fopen(trace_file, "w");
    if (!c->trace) {
      perror(trace_file);
      return EXIT_LOAD_ERROR;
    }
  } else if (trace) {
    c->trace = stderr;
  }

  /* Reset state.  crt0 sets sp itself; a starting value helps programs
   * that run without it. */
  c->psw = PSW_S | PSW_I | PSW_M | PSW_V | PSW_e;
  c->r[29] = (c->memsize - 16) & ~7u;
  uint32_t entry = c->prog.entry / 4;
  c->q[0] = entry;
  c->q[1] = entry + 1;
  c->q[2] = entry + 2;
  c->prev_pc = entry;

  if (!setjmp(c->stop)) {
    for (;;)
      step(c);
  }
  fflush(stdout);
  if (stats)
    fprintf(stderr,
            "mipsx-sim: cycles %" PRIu64 ", instructions %" PRIu64
            ", squashed %" PRIu64 ", store stalls %" PRIu64
            ", delay slots %" PRIu64 " (nop %" PRIu64 ")%s\n",
            c->cycles, c->instret, c->squashed, c->stalls, c->slots,
            c->slot_nops, c->warnings ? ", hazards reported" : "");
  if (c->hz == HAZ_WARN && c->warnings)
    fprintf(stderr, "mipsx-sim: %" PRIu64 " hazard warning(s)\n",
            c->warnings);
  if (c->trace && c->trace != stderr)
    fclose(c->trace);
  return c->stop_status;
}
