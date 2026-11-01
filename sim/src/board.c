/* SPA3000 board model: address decode, options and the observable log.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Address map from peripherals.md §1.  See board.h for the sources.
 */
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "board.h"

int board_init(struct board *b, uint8_t *ram, uint32_t ramsize,
               const char *flash_path, double watchdog_s, FILE *log) {
  memset(b, 0, sizeof *b);
  b->ram = ram;
  b->ramsize = ramsize;
  b->log = log;
  sysctl_init(b);
  timer_init(b);
  watchdog_init(b, watchdog_s);
  return flash_init(b, flash_path);
}

void board_logf(struct board *b, const char *fmt, ...) {
  va_list ap;
  if (!b->log)
    return;
  fflush(stdout);
  fprintf(b->log, "mipsx-sim: board: cycle %" PRIu64 " (%.6f s): ", b->cycles,
          (double)b->cycles / (double)BOARD_HZ);
  va_start(ap, fmt);
  vfprintf(b->log, fmt, ap);
  va_end(ap);
  fputc('\n', b->log);
}

static int bus_error(struct board *b, const char *fmt, ...)
    __attribute__((format(printf, 2, 3)));
static int bus_error(struct board *b, const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(b->err, sizeof b->err, fmt, ap);
  va_end(ap);
  return BUS_ERROR;
}

static uint32_t ram_get(const uint8_t *p, unsigned size) {
  switch (size) {
  case 4:
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 |
           p[3];
  case 2: return (uint32_t)p[0] << 8 | p[1];
  default: return p[0];
  }
}

static void ram_put(uint8_t *p, unsigned size, uint32_t v) {
  switch (size) {
  case 4:
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
    break;
  case 2: p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; break;
  default: p[0] = (uint8_t)v; break;
  }
}

/* The DRAM aliases at 0x02000000 and 0x12000000 [spec: peripherals.md §1;
 * that they alias address 0 is Hypothesis, address bit 28 being the
 * cached/uncached distinction as for flash].  Returns the RAM offset or
 * -1. */
static int64_t dram_alias(const struct board *b, uint32_t addr, unsigned size) {
  uint32_t base;
  if (addr - BOARD_DRAM_ALIAS1 < b->ramsize)
    base = BOARD_DRAM_ALIAS1;
  else if (addr - BOARD_DRAM_ALIAS2 < b->ramsize)
    base = BOARD_DRAM_ALIAS2;
  else
    return -1;
  if (b->ramsize - (addr - base) < size)
    return -1;
  return addr - base;
}

/* Flash window: 1 MB repeating through 16 MB at both bases [spec:
 * peripherals.md §1; flash.md §1].  Returns the offset in the part or -1. */
static int64_t flash_offset(uint32_t addr) {
  if (addr - BOARD_FLASH_BASE1 < BOARD_FLASH_WINDOW ||
      addr - BOARD_FLASH_BASE2 < BOARD_FLASH_WINDOW)
    return addr & (FLASH_SIZE - 1);
  return -1;
}

static int in_sysctl(uint32_t addr) {
  /* Address bits 1-0 are probably not decoded [spec: peripherals.md §1,
   * §3: the boot code uses 0x14000000, the application 0x14000003]. */
  return (addr & ~3u) == BOARD_SYSCTL_BASE;
}

static int in_rtl8019(uint32_t addr) {
  return addr - BOARD_RTL8019_BASE < BOARD_RTL8019_SPAN;
}

enum bus_result board_read(struct board *b, uint32_t addr, unsigned size,
                           uint32_t *v) {
  int64_t off;
  if ((off = dram_alias(b, addr, size)) >= 0) {
    *v = ram_get(b->ram + off, size);
    return BUS_OK;
  }
  if ((off = flash_offset(addr)) >= 0) {
    *v = flash_read(b, (uint32_t)off, size);
    return BUS_OK;
  }
  if (in_sysctl(addr))
    return sysctl_read(b, addr, size, v);
  if (in_rtl8019(addr))
    return bus_error(b, "load from RTL8019AS register %u at 0x%08x: the "
                     "Ethernet controller is not modelled yet",
                     (addr - BOARD_RTL8019_BASE) / 0x40, addr);
  if (addr - BOARD_PROBE_BASE < BOARD_FLASH_WINDOW) {
    /* Nothing answers at 0x18000000 on this board [spec: peripherals.md
     * §1, Simulated].  What an unanswered read returns is not known; 0
     * is a modelling choice (Hypothesis) and is not a flash ID code. */
    *v = 0;
    return BUS_OK;
  }
  if (addr - BOARD_ONCHIP_BASE < BOARD_ONCHIP_SIZE) {
    uint32_t o = addr - BOARD_ONCHIP_BASE;
    if (o - TIMER_BLOCK_OFF < TIMER_BLOCK_SIZE)
      return timer_read(b, o, size, v);
    return bus_error(b, "load from on-chip register 0x%08x, which is not "
                     "modelled yet (peripherals.md §2)", addr);
  }
  return BUS_UNMAPPED;
}

enum bus_result board_write(struct board *b, uint32_t addr, unsigned size,
                            uint32_t v) {
  int64_t off;
  if ((off = dram_alias(b, addr, size)) >= 0) {
    ram_put(b->ram + off, size, v);
    return BUS_OK;
  }
  if ((off = flash_offset(addr)) >= 0) {
    flash_write(b, (uint32_t)off, size, v);
    return BUS_OK;
  }
  if (in_sysctl(addr))
    return sysctl_write(b, addr, size, v);
  if (in_rtl8019(addr))
    return bus_error(b, "store to RTL8019AS register %u at 0x%08x: the "
                     "Ethernet controller is not modelled yet",
                     (addr - BOARD_RTL8019_BASE) / 0x40, addr);
  if (addr - BOARD_PROBE_BASE < BOARD_FLASH_WINDOW)
    return BUS_OK; /* nothing there to take the write [spec: §1] */
  if (addr - BOARD_ONCHIP_BASE < BOARD_ONCHIP_SIZE) {
    uint32_t o = addr - BOARD_ONCHIP_BASE;
    if (o - TIMER_BLOCK_OFF < TIMER_BLOCK_SIZE)
      return timer_write(b, o, size, v);
    return bus_error(b, "store to on-chip register 0x%08x, which is not "
                     "modelled yet (peripherals.md §2)", addr);
  }
  return BUS_UNMAPPED;
}

int board_fetch(struct board *b, uint32_t addr, uint32_t *word) {
  int64_t off;
  if ((off = dram_alias(b, addr, 4)) >= 0) {
    *word = ram_get(b->ram + off, 4);
    return 1;
  }
  if ((off = flash_offset(addr)) >= 0) {
    *word = flash_read(b, (uint32_t)off, 4);
    return 1;
  }
  return 0;
}

int board_pending_irq(const struct board *b) {
  /* Pending = status & enable & 0x3FFF [spec: peripherals.md §4]. */
  return (b->timer.istat & b->timer.ien & INTC_MASK) != 0;
}

unsigned board_step(struct board *b, uint64_t cycles) {
  unsigned flags = 0;
  b->cycles = cycles;
  timer_step(b);
  if (watchdog_step(b))
    flags |= BOARD_WATCHDOG;
  /* Interrupt suppress [spec: peripherals.md §4; Hypothesis, strong]: a
   * store of S to 0x4028 holds interrupts off for the next 15 - S
   * instructions.  board_step runs once per instruction issued, including
   * a squashed delay slot (modelling choice: the spec counts instructions
   * and says nothing about squashed slots), so this instruction is one of
   * the held-off ones while the count is still above zero. */
  int held = b->timer.suppress > 0;
  if (held)
    b->timer.suppress--;
  if (board_pending_irq(b) && !held)
    flags |= BOARD_IRQ;
  return flags;
}

void board_stats(const struct board *b, FILE *f) {
  fprintf(f, "mipsx-sim: board: watchdog kicks %" PRIu64 ", flash programs %"
          PRIu64 ", sector erases %" PRIu64 "\n",
          b->wdog.kicks, b->flash.programs, b->flash.erases);
}
