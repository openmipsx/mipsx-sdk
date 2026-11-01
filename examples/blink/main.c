/* main.c: blink the SPA3000's status LEDs.  The first image for the
 * board (open-source stack plan §4, step 2).
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Order of events (peripherals.md §7.2 for what the stock firmware does
 * first; README.md for why):
 *
 *   1. Interrupts stay masked (PSW bit 4) and the interrupt enable
 *      register is cleared.
 *   2. Watchdog kick (§5).  Kicks continue at every LED toggle and
 *      inside every flash operation.
 *   3. Dead-man net: a boot record without this program's slot is
 *      written (bootrec.c).  LEDs off meanwhile.
 *   4. Timer and port 0 set-up; with BLINK_WATCHDOG=1 the watchdog is
 *      enabled now that kicking runs.
 *   5. Blink: toggle every 500 ms (DEADMAN armed or restored), every
 *      1000 ms if the net was skipped, every 125 ms if a flash operation
 *      failed.
 *   6. After ARM_SECONDS of blinking, the record is rewritten with the
 *      slot restored; the LEDs pause for the second or two that takes.
 *   7. With BLINK_KICK_STOP_S set, kicking stops that many seconds after
 *      the restore (the P1 time-out experiment).
 */
#include "board.h"
#include "board_io.h"
#include "bootrec.h"
#include "hal.h"

#ifndef ARM_SECONDS
#define ARM_SECONDS 15
#endif
#ifndef BLINK_WATCHDOG
#define BLINK_WATCHDOG 0
#endif
#ifndef BLINK_KICK_STOP_S
#define BLINK_KICK_STOP_S 0
#endif

#ifdef BLINK_SIM
void sim_model_init(int argc, char **argv);
void sim_model_exit(int status);
#endif

static struct bootrec rec;          /* .bss */
static enum deadman_state state;    /* .bss */

static uint32_t period_ms(void)
{
    switch (state) {
    case DEADMAN_ARMED:
    case DEADMAN_RESTORED:
        return 500;
    case DEADMAN_FAILED:
        return 125;
    default:
        return 1000;
    }
}

int main(int argc, char **argv)
{
    uint32_t toggles = 0, on = 0, elapsed_ms = 0, since_restore_ms = 0;
    (void)argc;
    (void)argv;
    (void)toggles;
    (void)since_restore_ms;
#ifdef BLINK_SIM
    sim_model_init(argc, argv);
#endif

    /* 1. Interrupts masked, none enabled. */
    hal_psw_write(hal_psw_read() | PSW_INTERRUPT_MASK);
    hal_reg_write(REG_INT_ENABLE, 0);
    /* 2. First kick. */
    wd_kick();
    /* 3. The net, before anything else.  Nothing in .data has been
       written yet, which bootrec_section_is_this_program() needs. */
    state = deadman_arm(&rec);
    wd_kick();
    /* 4. Timer, LEDs (off first: data before direction, §6). */
    timer_init();
    leds_set(0);
#if BLINK_WATCHDOG
    wd_enable();
#endif
    hal_log("blink: start");

    /* 5. Blink forever. */
    for (;;) {
        uint32_t p = period_ms();
        on = !on;
        leds_set((int)on);
        wd_kick();
        delay_ms(p);
        toggles++;
        elapsed_ms += p;
        if (state == DEADMAN_ARMED && elapsed_ms >= ARM_SECONDS * 1000u) {
            /* 6. Healthy so far: put the slot back. */
            hal_log("blink: healthy, restoring the boot record");
            state = deadman_restore(&rec);
            wd_kick();
        }
        if (state == DEADMAN_RESTORED) {
            since_restore_ms += p;
#if BLINK_KICK_STOP_S
            if (since_restore_ms >= BLINK_KICK_STOP_S * 1000u) {
                hal_log("blink: kicking stopped");
                wd_stop_kicking();
            }
#endif
#ifdef BLINK_SIM
            if (since_restore_ms >= 2000)
                sim_model_exit(0);
#endif
        }
#ifdef BLINK_SIM
        if (state != DEADMAN_ARMED && state != DEADMAN_RESTORED &&
            toggles >= 6)
            sim_model_exit(0);
#endif
    }
}
