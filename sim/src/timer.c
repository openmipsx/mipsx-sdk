/* SPA3000 board model: the on-chip timer, interrupt controller and GPIO
 * block at 0x20004000.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * [spec: peripherals.md §2 (offsets 0x4000-0x4038), §4, §5].
 */
#include <stdio.h>
#include <string.h>

#include "board.h"

/* The count passes to 0 after 2^32 cycles when it is written 0. */
#define COUNT_PERIOD (1ull << 32)

static uint64_t next_zero(uint32_t base, uint64_t at) {
  /* The count reaches 0 after (2^32 - base) cycles [spec: §4, counts up
   * one per cycle, interrupt when it passes from negative to zero]. */
  return at + (COUNT_PERIOD - base);
}

void timer_init(struct board *b) {
  struct timer *t = &b->timer;
  memset(t, 0, sizeof *t);
  /* Reset values are not known (the firmware writes 0x400C = 0 and
   * 0x402C = 0x36, 0x4030 = 0x44 early, §7.2).  The count starts at 0 and
   * runs from reset (Hypothesis: whether 0x4000 starts it is not known). */
  t->next_zero = next_zero(0, 0);
}

void intc_raise(struct board *b, uint32_t bits) {
  b->timer.istat |= bits & INTC_MASK;
}

void timer_step(struct board *b) {
  struct timer *t = &b->timer;
  while (b->cycles >= t->next_zero) {
    /* Negative-to-zero crossing [spec: §4]: status bit 1 [spec: §4 table]. */
    intc_raise(b, INTC_BIT_TIMER);
    t->next_zero += COUNT_PERIOD;
  }
}

static uint32_t count_now(const struct board *b) {
  return b->timer.count_base + (uint32_t)(b->cycles - b->timer.count_cycle);
}

static int timer_error(struct board *b, const char *what, uint32_t off) {
  snprintf(b->err, sizeof b->err, "%s on-chip register 0x%08x", what,
           BOARD_ONCHIP_BASE + off);
  return BUS_ERROR;
}

/* All accesses the spec describes are word wide [spec: §7.1 "all word
 * writes"]; narrower ones are not described and are errors. */
enum bus_result timer_read(struct board *b, uint32_t off, unsigned size,
                           uint32_t *v) {
  struct timer *t = &b->timer;
  if (size != 4)
    return timer_error(b, "non-word load from", off);
  switch (off) {
  case TIMER_REG_COUNT:
    *v = count_now(b); /* [spec: §4: the handler reads it back] */
    return BUS_OK;
  case TIMER_REG_IEN:
    *v = t->ien; /* [spec: §2 0x4034, §4] */
    return BUS_OK;
  case TIMER_REG_ISTAT:
    *v = t->istat; /* [spec: §2 0x4038, §4] */
    return BUS_OK;
  case TIMER_REG_GPIO_WD:
    *v = t->gpio_wd; /* [spec: §2 0x402C] */
    return BUS_OK;
  case TIMER_REG_GPIO_SI:
    /* [spec: §2 0x4030, §8].  The SLIC/DAA bus is not modelled yet: the
     * latch reads back as written, so a released data line reads as the
     * last value driven, not as the spec's "nobody drives it reads 1". */
    *v = t->gpio_si;
    return BUS_OK;
  case TIMER_REG_ACK:
  case TIMER_REG_ACK13:
    return timer_error(b, "load from write-only acknowledge", off);
  case TIMER_REG_ISUPP:
    /* What a read gives is not described [spec: §4]; the last value
     * written is a modelling choice. */
    *v = t->latch[(off - TIMER_BLOCK_OFF) / 4];
    return BUS_OK;
  case TIMER_REG_CTL: case TIMER_REG_CFG: case TIMER_REG_4008:
  case TIMER_REG_4014:
    /* Latches with unknown roles [spec: §2]: read back as written. */
    *v = t->latch[(off - TIMER_BLOCK_OFF) / 4];
    return BUS_OK;
  default:
    return timer_error(b, "load from unknown", off);
  }
}

enum bus_result timer_write(struct board *b, uint32_t off, unsigned size,
                            uint32_t v) {
  struct timer *t = &b->timer;
  if (size != 4)
    return timer_error(b, "non-word store to", off);
  switch (off) {
  case TIMER_REG_COUNT:
    /* [spec: §4]: the firmware writes -810,000 to start and writes back
     * count - 809,930 each tick, keeping the overshoot. */
    t->count_base = v;
    t->count_cycle = b->cycles;
    t->next_zero = next_zero(v, b->cycles);
    return BUS_OK;
  case TIMER_REG_ACK:
    /* Timer interrupt acknowledge, any write [spec: §2 0x4010]. */
    t->istat &= ~INTC_BIT_TIMER;
    return BUS_OK;
  case TIMER_REG_ACK13:
    /* Acknowledge for bit 13 [spec: §2 0x4024; Hypothesis, strong]. */
    t->istat &= ~INTC_BIT_SYSCTL;
    return BUS_OK;
  case TIMER_REG_IEN:
    t->ien = v & INTC_MASK; /* [spec: §4: 14 sources] */
    return BUS_OK;
  case TIMER_REG_ISTAT:
    /* What a write to the status register does is not described; the
     * sources are acknowledged through 0x4010 and 0x4024 [spec: §2].  The
     * write is ignored (modelling choice). */
    return BUS_OK;
  case TIMER_REG_GPIO_WD: {
    /* GPIO port; a low-then-high pulse on bit 2 kicks the watchdog
     * [spec: §2 0x402C, §5; Hypothesis, strong]. */
    uint32_t old = t->gpio_wd;
    t->gpio_wd = v;
    if (!(old & 4) && (v & 4))
      watchdog_kick(b);
    return BUS_OK;
  }
  case TIMER_REG_GPIO_SI:
    t->gpio_si = v; /* [spec: §2 0x4030]; bus traffic not modelled yet */
    return BUS_OK;
  case TIMER_REG_ISUPP:
    /* Interrupt suppress [spec: §2 0x4028 row, §4 "Interrupt suppress";
     * Hypothesis, strong]: writing S (bits 3-0) holds off interrupts for
     * the next 15 - S instructions: 0 gives 15, 0xE gives 1, 0xF none.
     * The upper bits are not described and are ignored.  The count runs
     * in board_step. */
    t->latch[(off - TIMER_BLOCK_OFF) / 4] = v;
    t->suppress = ISUPP_MAX - (v & 0xF);
    return BUS_OK;
  case TIMER_REG_CTL: case TIMER_REG_CFG: case TIMER_REG_4008:
  case TIMER_REG_4014:
    t->latch[(off - TIMER_BLOCK_OFF) / 4] = v; /* [spec: §2, roles unknown] */
    return BUS_OK;
  default:
    return timer_error(b, "store to unknown", off);
  }
}
