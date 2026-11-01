/* hal.h: the few accesses the blink example makes to the hardware.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * On the device these are volatile loads and stores at the addresses in
 * board.h.  In the simulator build (BLINK_SIM) they are functions in
 * sim/model.c, which models the timer, the system-control device and
 * the flash chip well enough to run the start-up logic.
 */
#ifndef BLINK_HAL_H
#define BLINK_HAL_H

#include <stdint.h>
#include "board.h"

#ifdef BLINK_SIM

uint32_t hal_reg_read(uint32_t off);
void hal_reg_write(uint32_t off, uint32_t value);
void hal_sc_write(uint8_t byte);
uint8_t hal_sc_read(void);
uint8_t hal_flash_read(uint32_t off);
void hal_flash_write(uint32_t off, uint8_t value);
uint32_t hal_psw_read(void);
void hal_psw_write(uint32_t psw);
/* Logging: a no-op on the device. */
void hal_log(const char *text);
void hal_log_hex(const char *text, uint32_t value);
void hal_delay_loop_hint(void);

#else

static inline uint32_t hal_reg_read(uint32_t off)
{
    return *(volatile uint32_t *)(ONCHIP_BASE + off);
}

static inline void hal_reg_write(uint32_t off, uint32_t value)
{
    *(volatile uint32_t *)(ONCHIP_BASE + off) = value;
}

static inline void hal_sc_write(uint8_t byte)
{
    *(volatile uint8_t *)SYSCTL_ADDR = byte;
}

static inline uint8_t hal_sc_read(void)
{
    return *(volatile uint8_t *)SYSCTL_ADDR;
}

static inline uint8_t hal_flash_read(uint32_t off)
{
    return *(volatile uint8_t *)(FLASH_BASE + off);
}

static inline void hal_flash_write(uint32_t off, uint8_t value)
{
    *(volatile uint8_t *)(FLASH_BASE + off) = value;
}

/* processor-es3890.md §10: PSW bit 4 masks interrupts. */
static inline uint32_t hal_psw_read(void)
{
    uint32_t v;
    __asm__ volatile("movfrs psw,%0" : "=r"(v));
    return v;
}

static inline void hal_psw_write(uint32_t psw)
{
    __asm__ volatile("movtos %0,psw" : : "r"(psw));
}

static inline void hal_log(const char *text) { (void)text; }
static inline void hal_log_hex(const char *text, uint32_t value)
{
    (void)text;
    (void)value;
}
static inline void hal_delay_loop_hint(void) {}

#endif

#define PSW_INTERRUPT_MASK 0x10u

#endif
