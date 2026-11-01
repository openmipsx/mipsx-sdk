/* SPA3000 board model: the watchdog.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * [spec: peripherals.md §5].  Kick: a low-then-high pulse on 0x2000402C
 * bit 2 (detected in timer.c).  Enable: system-control reg 3 bit 7
 * (sysctl.c).  The timeout is not known; the firmware relies on it being
 * longer than 5.03 s, so the default here is 8 s, and whether the
 * watchdog runs before reg 3 bit 7 is set is not known either: the model
 * does not run it until then (Hypothesis, as the spec's advice to new
 * firmware assumes).
 */
#include <math.h>

#include "board.h"

void watchdog_init(struct board *b, double seconds) {
  struct watchdog *w = &b->wdog;
  w->enabled = 0;
  w->timeout = seconds > 0 ? (uint64_t)llround(seconds * (double)BOARD_HZ) : 0;
  w->deadline = 0;
  w->last_kick = 0;
  w->kicks = 0;
}

void watchdog_enable(struct board *b, int on) {
  struct watchdog *w = &b->wdog;
  if (on && !w->enabled) {
    w->deadline = b->cycles + w->timeout;
    board_logf(b, "watchdog enabled (timeout %.3f s)",
               (double)w->timeout / (double)BOARD_HZ);
  } else if (!on && w->enabled) {
    board_logf(b, "watchdog disabled");
  }
  w->enabled = on;
}

void watchdog_kick(struct board *b) {
  struct watchdog *w = &b->wdog;
  w->kicks++;
  w->last_kick = b->cycles;
  if (w->enabled)
    w->deadline = b->cycles + w->timeout;
}

/* Returns 1 when the watchdog bites: enabled, a timeout set, and no kick
 * for that long. */
int watchdog_step(struct board *b) {
  struct watchdog *w = &b->wdog;
  return w->enabled && w->timeout && b->cycles >= w->deadline;
}
