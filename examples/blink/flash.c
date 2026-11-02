/* flash.c: Am29LV081B driver, written from the AMD datasheet alone
 * (Publication 21525 Rev D, 4 June 2004: "Command Definitions", Table 4,
 * "Write Operation Status", Figure 5, Table 5) and flash.md §1 for how
 * the chip sits on this board.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * The chip is byte-wide and reached through FLASH_BASE (board.h).
 * Commands are written as bytes to the unlock addresses 0x555 and 0x2AA
 * (Table 4 says the address bits are don't-cares for command cycles on
 * this device; the classic addresses are used anyway, as the stock
 * firmware does, flash.md §1).  Completion is detected by Data# Polling
 * on DQ7 with DQ5 as the "exceeded timing limits" flag (Figure 5): the
 * datasheet's algorithm, including the re-read of DQ7 after DQ5 goes
 * high.  Every polling loop also has an iteration cap, so that a chip
 * that never answers cannot hang the program, and calls
 * flash_poll_hook() now and then so the watchdog is kicked.  (The stock
 * driver does not kick; its installers turn the watchdog off for the
 * install instead, flash.md §1.  Here variant 2 has enabled the
 * watchdog before the restore, and the kicks keep it satisfied.)
 *
 * Interrupts are masked for the whole program, so the 50 us sector-erase
 * time-out window (Table 4 note, "Sector Erase Command Sequence") cannot
 * be interrupted; only one sector is ever queued per erase anyway.
 */
#include "flash.h"
#include "board.h"
#include "hal.h"

#define CMD_UNLOCK1_ADDR 0x555u
#define CMD_UNLOCK2_ADDR 0x2AAu
#define CMD_UNLOCK1      0xAAu
#define CMD_UNLOCK2      0x55u
#define CMD_RESET        0xF0u
#define CMD_AUTOSELECT   0x90u
#define CMD_PROGRAM      0xA0u
#define CMD_ERASE_SETUP  0x80u
#define CMD_SECTOR_ERASE 0x30u

#define DQ7 0x80u
#define DQ5 0x20u

/* Polling caps, in loop iterations.  Each iteration is a few dozen
   cycles at most, so these are far above the datasheet maxima of 300 us
   per byte and 15 s per sector erase at 81 MHz. */
#define PROGRAM_POLL_CAP   2000000u
#define ERASE_POLL_CAP     400000000u
#define POLL_HOOK_INTERVAL 0x10000u

/* flash.md §1, "Driver behaviour": section A makes 3 erase attempts per
   sector and 9 program attempts per byte (section B 5 and 61). */
#define ERASE_RETRIES   3
#define PROGRAM_RETRIES 9

static void unlock(void)
{
    hal_flash_write(CMD_UNLOCK1_ADDR, CMD_UNLOCK1);
    hal_flash_write(CMD_UNLOCK2_ADDR, CMD_UNLOCK2);
}

static void reset_to_read(void)
{
    hal_flash_write(0, CMD_RESET);
}

uint8_t flash_read8(uint32_t off)
{
    return hal_flash_read(off);
}

uint32_t flash_read32(uint32_t off)
{
    return ((uint32_t)hal_flash_read(off) << 24) |
           ((uint32_t)hal_flash_read(off + 1) << 16) |
           ((uint32_t)hal_flash_read(off + 2) << 8) |
           hal_flash_read(off + 3);
}

void flash_read(uint32_t off, uint8_t *dst, uint32_t len)
{
    while (len--)
        *dst++ = hal_flash_read(off++);
}

enum flash_result flash_identify(void)
{
    uint8_t mfr, dev;

    reset_to_read();
    unlock();
    hal_flash_write(CMD_UNLOCK1_ADDR, CMD_AUTOSELECT);
    mfr = hal_flash_read(0x00);   /* Table 4: X00 -> manufacturer code */
    dev = hal_flash_read(0x01);   /* X01 -> device code */
    reset_to_read();
    hal_log_hex("flash: manufacturer", mfr);
    hal_log_hex("flash: device", dev);
    if (mfr != FLASH_MFR_ID || dev != FLASH_DEV_ID)
        return FLASH_BAD_ID;
    return FLASH_OK;
}

/* Data# Polling (Figure 5) at address OFF until DQ7 equals bit 7 of
   WANT.  Returns 1 on success, 0 on DQ5 failure or time-out; in both
   failure cases the chip has been reset to reading array data. */
static int poll(uint32_t off, uint8_t want, uint32_t cap)
{
    uint32_t n;

    for (n = 0; n < cap; n++) {
        uint8_t d = hal_flash_read(off);
        if (((d ^ want) & DQ7) == 0)
            return 1;
        if (d & DQ5) {
            /* Figure 5 note 2: DQ7 may change at the same moment as DQ5,
               so read it once more before declaring failure. */
            d = hal_flash_read(off);
            if (((d ^ want) & DQ7) == 0)
                return 1;
            reset_to_read();
            return 0;
        }
        if ((n & (POLL_HOOK_INTERVAL - 1)) == POLL_HOOK_INTERVAL - 1)
            flash_poll_hook();
    }
    reset_to_read();
    return 0;
}

static int sector_is_erased(uint32_t sector_off)
{
    uint32_t i;
    for (i = 0; i < FLASH_SECTOR_SIZE; i++) {
        if (hal_flash_read(sector_off + i) != 0xFF)
            return 0;
        if ((i & 0xFFF) == 0xFFF)
            flash_poll_hook();
    }
    return 1;
}

enum flash_result flash_erase_sector(uint32_t sector_off)
{
    int attempt;

    if (sector_off != BOOT_BLOCK0 && sector_off != BOOT_BLOCK1)
        return FLASH_REFUSED;
    for (attempt = 0; attempt < ERASE_RETRIES; attempt++) {
        flash_poll_hook();
        /* Table 4, Sector Erase: AA, 55, 80, AA, 55, then 30 at the
           sector address. */
        unlock();
        hal_flash_write(CMD_UNLOCK1_ADDR, CMD_ERASE_SETUP);
        unlock();
        hal_flash_write(sector_off, CMD_SECTOR_ERASE);
        /* During the Embedded Erase algorithm DQ7 reads 0 at an address
           in the sector; 1 when it is done (Table 5). */
        if (poll(sector_off, 0xFF, ERASE_POLL_CAP) &&
            sector_is_erased(sector_off))
            return FLASH_OK;
        hal_log_hex("flash: erase attempt failed, sector", sector_off);
    }
    return FLASH_ERASE_FAILED;
}

static int program_byte(uint32_t off, uint8_t value)
{
    int attempt;

    for (attempt = 0; attempt < PROGRAM_RETRIES; attempt++) {
        /* Table 4, Program: AA, 55, A0, then the data at its address. */
        unlock();
        hal_flash_write(CMD_UNLOCK1_ADDR, CMD_PROGRAM);
        hal_flash_write(off, value);
        /* DQ7 is the complement of the datum until programming is done,
           then the datum itself (Table 5). */
        if (poll(off, value, PROGRAM_POLL_CAP) && hal_flash_read(off) == value)
            return 1;
    }
    return 0;
}

enum flash_result flash_program(uint32_t off, const uint8_t *src,
                                uint32_t len)
{
    uint32_t i;

    if (off + len > FLASH_SECTOR_SIZE * 2 || off + len < off)
        return FLASH_REFUSED;
    for (i = 0; i < len; i++) {
        uint8_t want = src[i];
        if (hal_flash_read(off + i) != want && !program_byte(off + i, want)) {
            hal_log_hex("flash: program failed at", off + i);
            return FLASH_PROGRAM_FAILED;
        }
        if ((i & 0x3FF) == 0x3FF)
            flash_poll_hook();
    }
    return FLASH_OK;
}
