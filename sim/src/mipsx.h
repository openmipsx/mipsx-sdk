/* MIPS-X (ES3890) instruction-set simulator: shared definitions.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Sources: linksys-spa3000/docs/spec/processor-es3890.md ("spec"),
 * mipsx-sdk/docs/abi.md ("abi") and the MIPS-X manual ("manual").
 * Bits are numbered from the least significant bit (bit 0), as in the spec.
 */
#ifndef MIPSX_H
#define MIPSX_H

#include <stdint.h>
#include <stdio.h>

#define EM_MIPS_X 51
#define EF_MIPSX_ES3890 0x00000001u
#define EF_MIPSX_VSHIFT 0x00000002u

/* Simulator I/O page (abi §13.5, extended here; see sim/README.md). */
#define IO_BASE      0xFFFF0000u
#define IO_SIZE      0x100u
#define IO_PUTCHAR   0x00u /* store, any width: low 8 bits to stdout */
#define IO_EXIT      0x04u /* store word: exit with value as status */
#define IO_CYCLE_LO  0x08u /* load word: cycle counter low (latches high) */
#define IO_CYCLE_HI  0x0Cu /* load word: latched cycle counter high */
#define IO_GETCHAR   0x10u /* load word: byte from stdin or -1 at EOF */
#define IO_PUTCHAR_ERR 0x14u /* store, any width: low 8 bits to stderr */
#define IO_INSTRET_LO 0x18u /* load word: instructions retired low (latches high) */
#define IO_INSTRET_HI 0x1Cu /* load word: latched instructions retired high */

/* Special register numbers (spec §6). */
#define SPEC_PSW 1
#define SPEC_MD  2
#define SPEC_PC  4

/* PSW bits.  Positions are from the manual's Figure 2-3, converted to
 * LSB-first numbering (manual bit k is our bit 31-k).  The spec does not
 * confirm them for the ES3890. Upper case = PSWcurrent, lower = PSWother. */
#define PSW_S  (1u << 0)  /* PC chain shifting enabled */
#define PSW_s  (1u << 1)
#define PSW_I  (1u << 2)  /* 0 if the exception was an interrupt */
#define PSW_i  (1u << 3)
#define PSW_M  (1u << 4)  /* interrupt mask */
#define PSW_m  (1u << 5)
#define PSW_V  (1u << 6)  /* overflow trap mask */
#define PSW_v  (1u << 7)
#define PSW_e  (1u << 8)  /* read-only */
#define PSW_E_MASK (0xFu << 9) /* read-only shift chain */
#define PSW_o  (1u << 28)
#define PSW_O  (1u << 29)
#define PSW_u  (1u << 30)
#define PSW_U  (1u << 31) /* user state */
#define PSW_CUR_MASK (PSW_S | PSW_I | PSW_M | PSW_V | PSW_O | PSW_U)
#define PSW_READONLY (PSW_e | PSW_E_MASK)

enum op {
  OP_INVALID = 0,
  /* memory */
  OP_LD, OP_ST, OP_LDBU, OP_LDB, OP_LDHU, OP_LDH, OP_STB, OP_STH,
  /* branches */
  OP_BEQ, OP_BNE, OP_BHS, OP_BLO, OP_BLT, OP_BGE,
  /* compute */
  OP_ADD, OP_SUB, OP_SUBNC, OP_AND, OP_BIC, OP_NOT, OP_OR, OP_XOR,
  OP_MSTART, OP_MSTEP, OP_DSTEP, OP_ROTLB, OP_ROTLCB, OP_SH, OP_ASR,
  /* compute immediate */
  OP_ADDI, OP_JSPCI, OP_MOVFRS, OP_MOVTOS, OP_JPC, OP_JPCRS, OP_HSC, OP_TRAP,
  OP_COUNT
};

/* Instruction class flags. */
#define F_LOAD    0x01u
#define F_STORE   0x02u
#define F_BRANCH  0x04u
#define F_JUMP    0x08u /* jspci, jpc, jpcrs */
#define F_TRAPLIKE 0x10u /* trap, hsc */
#define F_ES3890  0x20u /* byte/halfword memory instruction */
#define F_MD      0x40u /* mstart, mstep, dstep */
#define F_MEM     (F_LOAD | F_STORE)
#define F_CTL     (F_BRANCH | F_JUMP | F_TRAPLIKE)

struct insn {
  uint32_t word;
  enum op op;
  unsigned flags;
  unsigned src1, src2, dest; /* register numbers as used by this insn */
  int32_t imm;               /* imm17, branch disp16, or shift amount n */
  unsigned sq;               /* branch squash bit */
  unsigned spec;             /* special register number */
  unsigned vector;           /* trap vector */
  uint32_t reads;            /* mask of general registers read */
  int wreg;                  /* general register written, or -1 */
  unsigned size;             /* memory access size in bytes */
  const char *why;           /* reason when op == OP_INVALID */
};

void mx_decode(uint32_t word, struct insn *in);
/* Disassemble into buf; pc_word is the instruction's word address (for
 * branch targets). */
void mx_disasm(const struct insn *in, uint32_t pc_word, char *buf, size_t n);
const char *mx_opname(enum op op);

/* ELF loading (elf.c). */
struct symbol {
  uint32_t addr;
  const char *name;
};

struct program {
  uint32_t entry;
  uint32_t flags;
  struct symbol *syms;
  size_t nsyms;
  char *strtab;
};

/* Loads into mem (big-endian, size memsize). Returns 0 on success, or
 * prints an error and returns -1. */
int elf_load(const char *path, uint8_t *mem, uint32_t memsize,
             struct program *prog);
/* Returns the symbol containing addr (nearest at or below), or NULL. */
const struct symbol *elf_symbolize(const struct program *prog, uint32_t addr);

#endif
