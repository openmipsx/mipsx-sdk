/* flash.h: Am29LV081B driver for the SPA3000's flash.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef BLINK_FLASH_H
#define BLINK_FLASH_H

#include <stdint.h>

enum flash_result {
    FLASH_OK = 0,
    FLASH_BAD_ID,        /* autoselect did not return 01h / 38h */
    FLASH_ERASE_FAILED,  /* DQ5 set, or the sector never read back erased */
    FLASH_PROGRAM_FAILED,/* DQ5 set, or the byte never read back */
    FLASH_REFUSED        /* the driver refuses to touch that sector */
};

/* Reads the autoselect codes (Table 4) and returns FLASH_OK if the chip
   is an Am29LV081B.  Leaves the chip reading array data. */
enum flash_result flash_identify(void);

uint8_t flash_read8(uint32_t off);
uint32_t flash_read32(uint32_t off);          /* big-endian bytes */
void flash_read(uint32_t off, uint8_t *dst, uint32_t len);

/* Erases one 64 KB sector and checks it reads back as 0xFF.  Only
   sectors 0 and 1 (the boot-record blocks) are allowed; anything else is
   FLASH_REFUSED, so that no bug here can reach the recovery program, the
   application or the factory record (flash.md §6). */
enum flash_result flash_erase_sector(uint32_t sector_off);

/* Programs LEN bytes at OFF and checks them.  Bytes that already hold
   the wanted value are skipped (an erased byte is 0xFF; only 1 -> 0
   transitions are possible, datasheet "Byte Program Command Sequence").
   The caller must have erased the range first. */
enum flash_result flash_program(uint32_t off, const uint8_t *src,
                                uint32_t len);

/* Called from the driver's polling loops so that the watchdog is kicked
   during a long erase (up to 15 s, datasheet "Erase and Programming
   Performance").  Provided by board.c. */
void flash_poll_hook(void);

#endif
