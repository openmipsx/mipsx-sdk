/* board.h: SPA3000 addresses and constants used by the blink example.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Every value here comes from the clean-side specifications in
 * openmipsx/devices (file and section given beside each one) or from
 * the Am29LV081B datasheet.  Nothing is taken from vendor code.
 */
#ifndef BLINK_BOARD_H
#define BLINK_BOARD_H

#include <stdint.h>

/* peripherals.md §1: on-chip registers.  Offsets from 0x20000000. */
#define ONCHIP_BASE        0x20000000u
#define REG_TIMER_PRE      0x4008u   /* written 0xFF at start-up (§2) */
#define REG_TIMER_COUNT    0x400Cu   /* counts up one per CPU cycle (§4) */
#define REG_TIMER_ACK      0x4010u   /* timer interrupt acknowledge (§2) */
#define REG_TIMER_4014     0x4014u   /* written 0 at start-up (§7.2 step 7) */
#define REG_GPIO_PRE       0x4028u   /* written before GPIO/system-control
                                        accesses; meaning unknown (§2, P2) */
#define REG_GPIO_WD        0x402Cu   /* bit 2: watchdog kick pulse (§5) */
#define REG_INT_ENABLE     0x4034u   /* interrupt enable; 0 = none (§4) */

/* peripherals.md §5: watchdog kick values on REG_GPIO_WD (bit 2 low
   then high; the other bits as the stock firmware leaves them). */
#define WD_KICK_LOW        0x32u
#define WD_KICK_HIGH       0x36u
#define WD_KICK_PRE        9u        /* REG_GPIO_PRE value before each write */

/* peripherals.md §3: the system-control register file, a byte-wide
   device at one address with a two-step protocol: address byte (reg << 1,
   bit 0 = 1 for a read), then one data byte. */
#define SYSCTL_ADDR        0x14000003u
#define SC_WATCHDOG        0x03u     /* bit 7 enables the watchdog (§5) */
#define SC_WATCHDOG_ENABLE 0xBCu     /* the value the stock firmware writes */
#define SC_PORT0_DATA      0x04u     /* §6 */
#define SC_PORT0_DIR       0x05u     /* 1 = driven, 0 = released (§6) */
#define SC_GPIO_PRE        0u        /* REG_GPIO_PRE value before an access */

/* peripherals.md §6: port 0 bit 3 drives the status LEDs D4, D7 and D8
   through Q21: driven 0 = on, driven 1 = off. */
#define PORT0_LED_BIT      (1u << 3)

/* peripherals.md §4: CPU clock in this board's mode. */
#define CPU_HZ             81000000u

/* flash.md §1, peripherals.md §1: 1 MB Am29LV081B at 0x0C000000, with
   0x1C000000 as the alias the stock flash driver uses (address bit 28;
   whether 0x0C000000 reads are cached is a Hypothesis, so the driver
   uses the 0x1C000000 form for everything it does).  Boot-record slots
   hold 0x0C000000 + offset. */
#define FLASH_BASE         0x1C000000u
#define FLASH_RECORD_BASE  0x0C000000u
#define FLASH_SIZE         0x100000u
#define FLASH_SECTOR_SIZE  0x10000u
#define FLASH_SECTORS      16u

/* Am29LV081B datasheet (AMD 21525 Rev D), Table 4 and Table 3. */
#define FLASH_MFR_ID       0x01u
#define FLASH_DEV_ID       0x38u

/* firmware-image-format.md §5, "Boot record" and "Boot-record blocks":
   sectors 0 and 1 alternate; the record is at the start of each. */
#define BOOT_BLOCK0        0x00000u
#define BOOT_BLOCK1        0x10000u
#define BR_SIZE            0xA0u
#define BR_SEQ             0x08u     /* sequence number, higher wins */
#define BR_SEQ_CHECK       0x0Cu     /* its complement */
#define BR_SLOT_TYPE1      0x20u     /* section B (recovery) */
#define BR_SLOT_TYPE2      0x30u     /* the application: us */
#define BR_SLOT_SIZE       0x10u
#define BR_SLOT_ADDR       0x08u     /* flash address of the table entry */
#define BR_SLOT_CHECK      0x0Cu     /* its complement */
#define BR_COPY_START      0x400u    /* header copy, event log, store and
                                        mirror: copied across unchanged */

/* firmware-image-format.md §3 and §4.1: table entry and packed header. */
#define ENTRY_TYPE         0x08u
#define ENTRY_DATA_OFFSET  0x0Cu
#define ENTRY_LENGTH       0x20u
#define ENTRY_SIZE         0x80u
#define PACKED_MAGIC       0x00060803u
#define PACKED_DIR_OFFSET  0x04u
#define PACKED_DIR_COUNT   0x08u
#define PACKED_LENGTH      0x10u
#define DIR_RECORD_SIZE    20u
#define DIR_COPY           0x01u     /* word 1 header offset, word 2 RAM
                                        address, word 3 length in words */

#endif
