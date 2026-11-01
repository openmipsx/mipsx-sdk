/* board.c: watchdog, system-control port, LEDs and the timer.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * All sequences follow peripherals.md (§3 system-control protocol, §4
 * timer, §5 watchdog, §6 port 0, §7.2 start-up).
 */
#include "board_io.h"
#include "board.h"
#include "hal.h"
#include "flash.h"

/* Mutable state lives in .bss (zero at start): nothing in .data may be
   written before bootrec_section_is_this_program() has compared the
   flash copy of the program with RAM (bootrec.c). */
static int timer_stuck;
static uint32_t timer_checks;
static uint32_t last_timer;
static int kicks_enabled_flag = 1;   /* .data: only ever written from main
                                        after the self-check */

void wd_kick(void)
{
    if (!kicks_enabled_flag)
        return;
    /* §5: a low-then-high pulse on bit 2 of 0x402C, with 0x4028 = 9
       written before each of the two writes. */
    hal_reg_write(REG_GPIO_PRE, WD_KICK_PRE);
    hal_reg_write(REG_GPIO_WD, WD_KICK_LOW);
    hal_reg_write(REG_GPIO_PRE, WD_KICK_PRE);
    hal_reg_write(REG_GPIO_WD, WD_KICK_HIGH);
}

void wd_stop_kicking(void)
{
    kicks_enabled_flag = 0;
}

void flash_poll_hook(void)
{
    wd_kick();
}

void sc_write(uint8_t reg, uint8_t value)
{
    /* §3: 0x4028 = 0 before each access; address byte (reg << 1, bit 0
       clear for a write), then the data byte, at the same address. */
    hal_reg_write(REG_GPIO_PRE, SC_GPIO_PRE);
    hal_sc_write((uint8_t)(reg << 1));
    hal_sc_write(value);
}

uint8_t sc_read(uint8_t reg)
{
    hal_reg_write(REG_GPIO_PRE, SC_GPIO_PRE);
    hal_sc_write((uint8_t)((reg << 1) | 1));
    return hal_sc_read();
}

void wd_enable(void)
{
    /* §5: system-control reg 3, bit 7; the stock firmware writes 0xBC
       and kicks twice straight after. */
    sc_write(SC_WATCHDOG, SC_WATCHDOG_ENABLE);
    wd_kick();
    wd_kick();
}

static uint8_t port0_data, port0_dir;   /* .bss: both 0 = released */

void port0_write(uint8_t data, uint8_t dir)
{
    /* §6: data first, then direction, so no pin glitches. */
    port0_data = data;
    port0_dir = dir;
    sc_write(SC_PORT0_DATA, data);
    sc_write(SC_PORT0_DIR, dir);
}

void leds_set(int on)
{
    /* §6: bit 3 driven 0 = LEDs on, driven 1 = off.  Only bit 3 is
       driven; the other port 0 pins stay released, as the boot code is
       believed to leave them (§6, Hypothesis). */
    uint8_t data = on ? (uint8_t)(port0_data & ~PORT0_LED_BIT)
                      : (uint8_t)(port0_data | PORT0_LED_BIT);
    port0_write(data, (uint8_t)(port0_dir | PORT0_LED_BIT));
}

void timer_init(void)
{
    /* §7.2 step 7, the plain timer writes the stock firmware makes: the
       timer control at 0x4000/0x4004 was set by the reset code (§7.1)
       and is left alone. */
    hal_reg_write(REG_TIMER_PRE, 0xFF);
    hal_reg_write(REG_TIMER_COUNT, 0);
    hal_reg_write(REG_TIMER_4014, 0);
    last_timer = hal_reg_read(REG_TIMER_COUNT);
}

uint32_t timer_now(void)
{
    return hal_reg_read(REG_TIMER_COUNT);
}

int timer_is_stuck(void)
{
    return timer_stuck;
}

/* Busy-wait iterations per millisecond when the timer does not count:
   a guess for a short loop at 81 MHz, only there so that the LEDs still
   blink (at some rate) and tell the user that much. */
#ifdef BLINK_SIM
#define LOOPS_PER_MS 4u
#else
#define LOOPS_PER_MS 20000u
#endif
#define STUCK_READS 100000u

void delay_ms(uint32_t ms)
{
    uint32_t cycles = ms * (CPU_HZ / 1000u);
    uint32_t start = timer_now();

    if (!timer_stuck) {
        for (;;) {
            uint32_t now = timer_now();
            if (now - start >= cycles)
                return;
            /* §4 says the count moves every cycle.  If it has not moved
               in a long run of reads, the timer is not running as the
               spec says: fall back to a counted loop. */
            if (now == last_timer) {
                if (++timer_checks >= STUCK_READS) {
                    timer_stuck = 1;
                    hal_log("timer: not counting, using a loop");
                    break;
                }
            } else {
                timer_checks = 0;
                last_timer = now;
            }
        }
    }
    {
        volatile uint32_t n = ms * LOOPS_PER_MS;
        while (n--)
            hal_delay_loop_hint();
    }
}
