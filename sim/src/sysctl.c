/* SPA3000 board model: the external system-control register file at
 * 0x14000003, with port 0 (AUX1) as an observable.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * [spec: peripherals.md §3, §5, §6].  A byte-wide device reached through
 * one address with a two-step protocol: an address byte (bits 7-1 the
 * register number, bit 0 = 1 for a read), then one data byte written or
 * read at the same address.
 */
#include <stdio.h>
#include <string.h>

#include "board.h"

/* Board-mode straps [spec: peripherals.md §3, "Board mode"]: on this board
 * reg 1 bit 4 and reg 2 bit 0 both read 1 (Simulated: chosen to match the
 * PLL straps; which bit is which strap is not known).  Reg 1 is read
 * before it is written, so the strap must be there from reset. */
#define STRAP1_VALUE 0x10u
#define STRAP2_VALUE 0x01u

void sysctl_init(struct board *b) {
  struct sysctl *s = &b->sysctl;
  memset(s, 0, sizeof *s);
  s->reg[SYSCTL_REG_STRAP1] = STRAP1_VALUE;
  s->reg[SYSCTL_REG_STRAP2] = STRAP2_VALUE;
  /* Before the first write the direction is presumably all released
   * [spec: §6, Hypothesis]; the data latch is not known and starts at 0. */
  memset(s->p0_logged, 0xFF, sizeof s->p0_logged);
}

static int sysctl_error(struct board *b, const char *msg) {
  snprintf(b->err, sizeof b->err, "%s", msg);
  return BUS_ERROR;
}

/* Port 0 pins [spec: peripherals.md §6, table; wiring Measured for bits
 * 0, 1, 2, 3 and 5, bit 4 predicted].  The log names each pin by its board
 * net and reports the level it drives, so a test can assert on timing. */
static const struct pin {
  const char *name;
  const char *low, *high; /* what a driven 0 and a driven 1 mean */
} pins[8] = {
  [0] = {"eth-reset", "released", "asserted"},     /* RTL8019AS RSTDRV, active high */
  [1] = {"si3210-reset", "asserted", "released"},  /* Si3210 RESET#, active low */
  [2] = {"si3050-reset", "asserted", "released"},  /* Si3050 RESET#, active low */
  [3] = {"led", "on", "off"},                      /* D4, D7, D8 through Q21: 0 = on */
  [4] = {"relay", "off", "on"},                    /* K1 driver */
  [5] = {"si3050-cs", "selected", "idle"},         /* Si3050 CS#, active low */
  [6] = {"aux1-6", "low", "high"},                 /* unknown net */
  [7] = {"aux1-7", "low", "high"},                 /* never written by the firmware */
};

static void port0_observe(struct board *b) {
  struct sysctl *s = &b->sysctl;
  for (unsigned i = 0; i < 8; i++) {
    uint8_t st = (s->p0_dir >> i & 1) ? (s->p0_data >> i & 1) ? 2 : 1 : 0;
    if (st == s->p0_logged[i])
      continue;
    if (s->p0_logged[i] == 0xFF && st == 0)
      continue; /* still released from reset: nothing to say */
    s->p0_logged[i] = st;
    if (st == 0)
      board_logf(b, "port0 %s released (input, latch %u)", pins[i].name,
                 s->p0_data >> i & 1);
    else
      board_logf(b, "port0 %s %s", pins[i].name,
                 st == 2 ? pins[i].high : pins[i].low);
  }
}

/* Recomputes the block's interrupt output and cascades a rising edge into
 * interrupt-controller bit 13 [spec: peripherals.md §3 regs 0x15/0x16,
 * §4 table].  Which bit of reg 0x15 masks which status bit is not known;
 * the model takes bit 3 as the block's enable and any set status bit as a
 * request (Hypothesis). */
static void sysctl_update_irq(struct board *b) {
  struct sysctl *s = &b->sysctl;
  int out = (s->reg[SYSCTL_REG_IMASK] & SYSCTL_IMASK_ENABLE) &&
            s->reg[SYSCTL_REG_ISTAT] != 0;
  if (out && !s->irq_out)
    intc_raise(b, INTC_BIT_SYSCTL);
  s->irq_out = out;
}

void sysctl_raise(struct board *b, uint8_t bits) {
  b->sysctl.reg[SYSCTL_REG_ISTAT] |= bits;
  sysctl_update_irq(b);
}

static void sysctl_reg_write(struct board *b, unsigned r, uint8_t v) {
  struct sysctl *s = &b->sysctl;
  s->written[r] = 1;
  switch (r) {
  case SYSCTL_REG_STRAP1:
    /* The strap bit is an input; the firmware writes the read value back
     * OR 0x21 [spec: §3].  The written bit 4 is kept as a latch but the
     * strap wins on a read. */
    s->reg[r] = v;
    break;
  case SYSCTL_REG_WDOG:
    s->reg[r] = v;
    /* Bit 7 enables the watchdog [spec: §3, §5; Hypothesis, strong]. */
    watchdog_enable(b, (v & 0x80) != 0);
    break;
  case SYSCTL_REG_P0_DATA:
    s->reg[r] = v;
    s->p0_data = v;
    port0_observe(b);
    break;
  case SYSCTL_REG_P0_DIR:
    s->reg[r] = v;
    s->p0_dir = v;
    port0_observe(b);
    break;
  case SYSCTL_REG_ISTAT:
    /* Write 1 to clear [spec: §3; Hypothesis, strong]. */
    s->reg[r] &= (uint8_t)~v;
    sysctl_update_irq(b);
    break;
  case SYSCTL_REG_IMASK:
    s->reg[r] = v;
    sysctl_update_irq(b);
    break;
  default:
    /* Control, port 1, clock/PLL settings, mode set-up: latches whose
     * effects are not modelled [spec: §3 table; roles unknown or not
     * needed here]. */
    s->reg[r] = v;
    break;
  }
}

static uint8_t sysctl_reg_read(struct board *b, unsigned r) {
  struct sysctl *s = &b->sysctl;
  switch (r) {
  case SYSCTL_REG_STRAP1:
    return (uint8_t)((s->reg[r] & ~0x10u) | STRAP1_VALUE);
  case SYSCTL_REG_STRAP2:
    return (uint8_t)((s->reg[r] & ~0x01u) | STRAP2_VALUE);
  default:
    /* Reads of unwritten registers other than the straps are not
     * specified; 0 is a modelling choice. */
    return s->reg[r];
  }
}

/* The device is byte wide [spec: §3].  Wider accesses are not described;
 * the model uses the low 8 bits of a store and fills every byte lane of a
 * load with the data byte (modelling choice). */
static uint32_t spread(uint8_t v, unsigned size) {
  uint32_t w = v;
  if (size >= 2)
    w |= w << 8;
  if (size == 4)
    w |= w << 16;
  return w;
}

enum bus_result sysctl_write(struct board *b, uint32_t addr, unsigned size,
                             uint32_t v) {
  struct sysctl *s = &b->sysctl;
  uint8_t byte = (uint8_t)v;
  (void)addr; (void)size;
  if (!s->have_addr) {
    /* Step 1: the address byte [spec: §3]. */
    s->cur_reg = byte >> 1;
    s->cur_read = byte & 1;
    s->have_addr = 1;
    return BUS_OK;
  }
  /* Step 2: the data byte of a write. */
  s->have_addr = 0;
  if (s->cur_read)
    return sysctl_error(b, "system-control data byte written after an "
                        "address byte that announced a read (peripherals.md "
                        "§3)");
  sysctl_reg_write(b, s->cur_reg, byte);
  return BUS_OK;
}

enum bus_result sysctl_read(struct board *b, uint32_t addr, unsigned size,
                            uint32_t *v) {
  struct sysctl *s = &b->sysctl;
  (void)addr;
  if (!s->have_addr)
    return sysctl_error(b, "system-control data byte read without an "
                        "address byte first (peripherals.md §3)");
  s->have_addr = 0;
  if (!s->cur_read)
    return sysctl_error(b, "system-control data byte read after an address "
                        "byte that announced a write (peripherals.md §3)");
  *v = spread(sysctl_reg_read(b, s->cur_reg), size);
  return BUS_OK;
}
