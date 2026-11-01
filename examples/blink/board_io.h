/* board_io.h: watchdog, system-control port, LEDs and timer (board.c).
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef BLINK_BOARD_IO_H
#define BLINK_BOARD_IO_H

#include <stdint.h>

void wd_kick(void);          /* peripherals.md §5 */
void wd_enable(void);        /* sets reg 3 bit 7; only after kicks run */
void wd_stop_kicking(void);  /* for the time-out experiment (P1) */

void sc_write(uint8_t reg, uint8_t value);   /* §3 */
uint8_t sc_read(uint8_t reg);

void port0_write(uint8_t data, uint8_t dir); /* §6 */
void leds_set(int on);

void timer_init(void);                       /* §4, §7.2 step 7 */
uint32_t timer_now(void);                    /* CPU cycles, wraps */
int timer_is_stuck(void);
void delay_ms(uint32_t ms);

#endif
