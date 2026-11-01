/* MIPS-X (ES3890) simulator: SPA3000 board model.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Clean-room model of the SPA3000's bus, written from
 * openmipsx/devices spa3000/peripherals.md ("peripherals.md"),
 * spa3000/flash.md ("flash.md") and the public AMD Am29LV081B datasheet.
 * Every register behaviour is tagged with its source.  Where the spec
 * marks a fact Hypothesis, the model follows it as written and says so.
 *
 * One peripheral per file: board.c (address decode, options, log),
 * sysctl.c (the external system-control register file), timer.c (the
 * on-chip timer and interrupt controller block at 0x20004000),
 * watchdog.c, flash.c.  The RTL8019AS, Si3210, Si3050, DMA columns and
 * DSP are not modelled yet; their addresses are errors that say so.
 */
#ifndef BOARD_H
#define BOARD_H

#include <stdint.h>
#include <stdio.h>

/* CPU clock in this board's mode [spec: peripherals.md §4, Hypothesis,
 * strong: 809,930 cycles = 10.000 ms]. */
#define BOARD_HZ 81000000ull

/* ---- Address map [spec: peripherals.md §1] ------------------------------ */
#define BOARD_DRAM_ALIAS1   0x02000000u /* DRAM again (alias: Hypothesis) */
#define BOARD_DRAM_ALIAS2   0x12000000u
#define BOARD_FLASH_BASE1   0x0C000000u /* 1 MB flash through a 16 MB window */
#define BOARD_FLASH_BASE2   0x1C000000u
#define BOARD_FLASH_WINDOW  0x01000000u
#define BOARD_SYSCTL_BASE   0x14000000u /* 0x14000000-0x14000003 */
#define BOARD_RTL8019_BASE  0x14000030u /* register n at + 0x40*n (§8) */
#define BOARD_RTL8019_SPAN  (0x40u * 32u)
#define BOARD_PROBE_BASE    0x18000000u /* probed for a second flash; nothing */
#define BOARD_ONCHIP_BASE   0x20000000u /* on-chip registers, 64 KB (§2) */
#define BOARD_ONCHIP_SIZE   0x00010000u

/* ---- System-control register file [spec: peripherals.md §3] ------------- */
#define SYSCTL_NREGS 128 /* 7-bit register number (address byte bits 7-1) */
#define SYSCTL_REG_CONTROL  0x00
#define SYSCTL_REG_STRAP1   0x01 /* bit 4: board-mode strap */
#define SYSCTL_REG_STRAP2   0x02 /* bit 0: second board-mode strap */
#define SYSCTL_REG_WDOG     0x03 /* bit 7 enables the watchdog (§5) */
#define SYSCTL_REG_P0_DATA  0x04 /* port 0 = AUX1 (§6) */
#define SYSCTL_REG_P0_DIR   0x05 /* 1 = driven output, 0 = released */
#define SYSCTL_REG_P1_DATA  0x06 /* port 1, probably AUX2 */
#define SYSCTL_REG_P1_DIR   0x07
#define SYSCTL_REG_IMASK    0x15 /* bit 3 set when interrupts are enabled */
#define SYSCTL_REG_ISTAT    0x16 /* write 1 to clear; bit 5 = RTL8019AS */
#define SYSCTL_ISTAT_RTL8019 0x20u
#define SYSCTL_IMASK_ENABLE  0x08u

struct sysctl {
  uint8_t reg[SYSCTL_NREGS];
  uint8_t written[SYSCTL_NREGS]; /* a read of an unwritten register is noted */
  int have_addr;      /* protocol step: 1 = address byte received */
  unsigned cur_reg;   /* register selected by the address byte */
  int cur_read;       /* address byte bit 0 */
  int irq_out;        /* the block's interrupt output, last computed */
  uint8_t p0_data, p0_dir;
  /* Port 0 pin states last logged: 0 = released, 1 = driven low,
   * 2 = driven high; 0xFF = not yet logged. */
  uint8_t p0_logged[8];
};

/* ---- Timer and interrupt controller [spec: peripherals.md §2, §4] -------- */
#define TIMER_BLOCK_OFF   0x4000u /* 0x20004000-0x2000403F */
#define TIMER_BLOCK_SIZE  0x40u
#define TIMER_REG_CTL     0x4000u /* reset code writes 1; role Hypothesis */
#define TIMER_REG_CFG     0x4004u /* reset code writes 0x1BDF3E; role Hypothesis */
#define TIMER_REG_4008    0x4008u /* written 0xFF at start-up; role unknown */
#define TIMER_REG_COUNT   0x400Cu /* counts up one per cycle (§4) */
#define TIMER_REG_ACK     0x4010u /* timer interrupt acknowledge, any write */
#define TIMER_REG_4014    0x4014u /* written 0 at start-up; role unknown */
#define TIMER_REG_ACK13   0x4024u /* acknowledge for interrupt bit 13 */
#define TIMER_REG_ISUPP   0x4028u /* interrupt suppress: 15 - S instructions (§4) */
#define ISUPP_MAX         15u
#define TIMER_REG_GPIO_WD 0x402Cu /* GPIO; bit 2 low-then-high = watchdog kick */
#define TIMER_REG_GPIO_SI 0x4030u /* GPIO carrying the SLIC/DAA bus (§8) */
#define TIMER_REG_IEN     0x4034u /* interrupt enable */
#define TIMER_REG_ISTAT   0x4038u /* interrupt status */
#define INTC_MASK         0x3FFFu /* 14 sources */
#define INTC_BIT_TIMER    (1u << 1)
#define INTC_BIT_DMA      (1u << 7)
#define INTC_BIT_SYSCTL   (1u << 13)

struct timer {
  uint32_t latch[TIMER_BLOCK_SIZE / 4]; /* registers with unknown roles */
  uint32_t count_base;    /* 0x400C value at count_cycle */
  uint64_t count_cycle;
  uint64_t next_zero;     /* cycle at which the count next passes to 0 */
  uint32_t ien, istat;
  uint32_t gpio_wd, gpio_si;
  /* Interrupt suppress [spec: peripherals.md §4, Hypothesis, strong]:
   * instructions still to run before an interrupt may be taken. */
  unsigned suppress;
};

/* ---- Watchdog [spec: peripherals.md §5] ---------------------------------- */
struct watchdog {
  int enabled;        /* system-control reg 3 bit 7 */
  uint64_t timeout;   /* cycles; 0 = never bites */
  uint64_t deadline;  /* cycle at which it bites, while enabled */
  uint64_t last_kick;
  uint64_t kicks;
};

/* ---- Flash: Am29LV081B [spec: flash.md §1; datasheet] -------------------- */
#define FLASH_SIZE    0x100000u /* 1 MB, sixteen 64 KB sectors */
#define FLASH_SECTOR  0x10000u
#define FLASH_MFR_ID  0x01u
#define FLASH_DEV_ID  0x38u

enum flash_state {
  FL_READ,       /* read array */
  FL_UNLOCK1,    /* 0xAA at 0x555 seen */
  FL_UNLOCK2,    /* then 0x55 at 0x2AA */
  FL_AUTOSELECT, /* 0x90: reads give the ID codes */
  FL_PROGRAM,    /* 0xA0: the next write is the byte to program */
  FL_ERASE1,     /* 0x80 seen; expects AA, 55, then 30 (sector) or 10 (chip) */
  FL_ERASE2,
  FL_ERASE3,
};

struct flash {
  uint8_t *data;
  enum flash_state state;
  uint64_t programs, erases;
};

/* ---- The board ------------------------------------------------------------ */
enum bus_result { BUS_OK = 0, BUS_UNMAPPED = 1, BUS_ERROR = 2 };

/* Flags returned by board_step. */
#define BOARD_IRQ       0x1 /* an enabled interrupt is pending and not suppressed */
#define BOARD_WATCHDOG  0x2 /* the watchdog has bitten */

struct board {
  uint8_t *ram;
  uint32_t ramsize;
  FILE *log;
  uint64_t cycles;    /* current cycle, set by board_step */
  char err[200];      /* message when a bus call returns BUS_ERROR */
  struct sysctl sysctl;
  struct timer timer;
  struct watchdog wdog;
  struct flash flash;
};

/* board.c */
int board_init(struct board *b, uint8_t *ram, uint32_t ramsize,
               const char *flash_path, double watchdog_s, FILE *log);
enum bus_result board_read(struct board *b, uint32_t addr, unsigned size,
                           uint32_t *v);
enum bus_result board_write(struct board *b, uint32_t addr, unsigned size,
                            uint32_t v);
/* Instruction fetch from outside RAM (DRAM aliases and flash). */
int board_fetch(struct board *b, uint32_t addr, uint32_t *word);
/* Advance to the given cycle, at the issue of one instruction (or squashed
 * slot); returns BOARD_* flags. */
unsigned board_step(struct board *b, uint64_t cycles);
void board_logf(struct board *b, const char *fmt, ...)
    __attribute__((format(printf, 2, 3)));
int board_pending_irq(const struct board *b);
void board_stats(const struct board *b, FILE *f);

/* sysctl.c */
void sysctl_init(struct board *b);
enum bus_result sysctl_read(struct board *b, uint32_t addr, unsigned size,
                            uint32_t *v);
enum bus_result sysctl_write(struct board *b, uint32_t addr, unsigned size,
                             uint32_t v);
/* For peripherals cascaded into reg 0x16 (the RTL8019AS, later). */
void sysctl_raise(struct board *b, uint8_t bits);

/* timer.c */
void timer_init(struct board *b);
enum bus_result timer_read(struct board *b, uint32_t off, unsigned size,
                           uint32_t *v);
enum bus_result timer_write(struct board *b, uint32_t off, unsigned size,
                            uint32_t v);
void timer_step(struct board *b);
void intc_raise(struct board *b, uint32_t bits);

/* watchdog.c */
void watchdog_init(struct board *b, double seconds);
void watchdog_enable(struct board *b, int on);
void watchdog_kick(struct board *b);
int watchdog_step(struct board *b);

/* flash.c */
int flash_init(struct board *b, const char *path);
uint32_t flash_read(struct board *b, uint32_t off, unsigned size);
void flash_write(struct board *b, uint32_t off, unsigned size, uint32_t v);

#endif
