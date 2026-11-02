/* bootrec.c: the boot record and the dead-man net.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Written from firmware-image-format.md §5 ("Boot record", "What each
 * program checks in a record", "Order", "Boot-record blocks"), §6
 * ("Rewriting the boot record from our own code") and flash.md §2, §4
 * and §6.
 *
 * The net.  The boot selector starts whatever the type 2 slot of the
 * newest boot record points at, every time, with no way for a running
 * application to ask for section B (§7.2).  So an application that
 * passes the boot checks and then hangs would be started forever.  This
 * program therefore:
 *
 *   1. On every start, before anything else that could hang, writes a
 *      new boot record (sequence + 1) into the inactive block with the
 *      type 2 slot blanked.  From then on a reset starts section B, the
 *      stock recovery program (§5 "Order" step 2 then 3; §6).
 *   2. After ARM_SECONDS of healthy blinking, writes another record
 *      (sequence + 2) into the other block with the slot restored, so
 *      the next reset starts this program again.
 *
 * The active block is the one the boot selector follows, since that is
 * the program the net has to steer: the block whose magic is intact,
 * of two the one with the higher sequence number compared unsigned,
 * and block 0 on a tie (§5, "What each program checks in a record").
 * Sections A and B choose differently (type 2 slot validity first,
 * block 1 on a tie) and must not be copied here.
 *
 * Each write follows what sections A and B do (§5, "Boot-record
 * blocks"): erase the inactive block, copy 0x1000-0xFFFF across (here
 * 0x400-0xFFFF: the header copy and the event log too, verbatim, which
 * §6 allows), write the record, its first byte last, so that a block
 * whose magic is incomplete is never taken as valid.
 *
 * The record is a copy of the one found with the sequence number, its
 * complement, the +0x10/+0x14 halfword pairs and the type 2 slot
 * rewritten: the pairs with the values both installers write, so that
 * the stock application finds all six of its validity flags clean in
 * the restored record (§6).  The type 1 slot is kept (§6).
 */
#include "bootrec.h"
#include "board.h"
#include "board_io.h"
#include "flash.h"
#include "hal.h"
#include "util.h"

#ifndef ARM_SECONDS
#define ARM_SECONDS 15
#endif

static const uint8_t BR_MAGIC[8] = {'S', 'I', 'P', 'U', 'R', 'A', ' ', '*'};
/* §5, "Boot record": 0x0400 and 0x1000, each followed by its complement. */
static const uint8_t BR_PAIRS_VALUE[8] = {0x04, 0x00, 0xFB, 0xFF,
                                          0x10, 0x00, 0xEF, 0xFF};

static int block_has_record(uint32_t block)
{
    uint8_t magic[8];
    flash_read(block, magic, 8);
    return memcmp(magic, BR_MAGIC, 8) == 0;
}

int bootrec_find_active(struct bootrec *r)
{
    int v0 = block_has_record(BOOT_BLOCK0);
    int v1 = block_has_record(BOOT_BLOCK1);
    uint32_t s0 = v0 ? flash_read32(BOOT_BLOCK0 + BR_SEQ) : 0;
    uint32_t s1 = v1 ? flash_read32(BOOT_BLOCK1 + BR_SEQ) : 0;
    uint32_t block;

    hal_log_hex("bootrec: block 0 valid", (uint32_t)v0);
    hal_log_hex("bootrec: block 0 seq", s0);
    hal_log_hex("bootrec: block 1 valid", (uint32_t)v1);
    hal_log_hex("bootrec: block 1 seq", s1);
    if (!v0 && !v1)
        return 0;
    if (v0 && v1)
        r->active = (s1 > s0) ? 1 : 0;    /* tie: block 0, as the selector */
    else
        r->active = v1 ? 1 : 0;
    block = r->active ? BOOT_BLOCK1 : BOOT_BLOCK0;
    r->seq = r->active ? s1 : s0;
    flash_read(block, r->record, BR_SIZE);
    memcpy(r->slot2, r->record + BR_SLOT_TYPE2, BR_SLOT_SIZE);
    return 1;
}

int bootrec_slot_usable(const uint8_t *slot)
{
    uint32_t addr = be32(slot + BR_SLOT_ADDR);
    uint32_t check = be32(slot + BR_SLOT_CHECK);
    return addr != 0xFFFFFFFFu && (addr | check) == 0xFFFFFFFFu;
}

int bootrec_section_is_this_program(uint32_t addr)
{
    uint32_t entry = addr & (FLASH_SIZE - 1);   /* §5: masked to the chip */
    uint32_t data, length, header, dir_off, count, i;
    int copies = 0;

    if (flash_read8(entry + ENTRY_TYPE) != 2)
        return 0;
    data = entry + flash_read32(entry + ENTRY_DATA_OFFSET);
    length = flash_read32(entry + ENTRY_LENGTH);
    if (data + length > FLASH_SIZE || length < 0x40)
        return 0;
    header = data;                     /* §4.1: the packed header */
    if (flash_read32(header) != PACKED_MAGIC)
        return 0;
    if (flash_read32(header + PACKED_LENGTH) != length)
        return 0;
    dir_off = flash_read32(header + PACKED_DIR_OFFSET);
    count = flash_read32(header + PACKED_DIR_COUNT);
    if (count > 64 || dir_off + count * DIR_RECORD_SIZE > length)
        return 0;
    for (i = 0; i < count; i++) {
        uint32_t rec = header + dir_off + i * DIR_RECORD_SIZE;
        uint32_t type = flash_read32(rec);
        uint32_t src, dest, bytes, k;
        if (type != DIR_COPY)
            continue;
        /* §4.4: word 1 is a header offset (relocation nibble 1), word 2
           the RAM address, word 3 the length in words. */
        src = header + flash_read32(rec + 4);
        dest = flash_read32(rec + 8);
        bytes = flash_read32(rec + 12) * 4;
        if (src + bytes > data + length || dest + bytes > 0x200000u)
            return 0;
        for (k = 0; k < bytes; k++) {
            if (flash_read8(src + k) != *(const uint8_t *)(dest + k))
                return 0;
            if ((k & 0xFFF) == 0xFFF)
                wd_kick();
        }
        copies++;
    }
    return copies > 0;
}

static int write_result(enum flash_result fr, const char *what)
{
    if (fr != FLASH_OK) {
        hal_log(what);
        hal_log_hex("bootrec: flash result", (uint32_t)fr);
    }
    return (int)fr;
}

int bootrec_write(struct bootrec *r, uint32_t newseq, int with_slot)
{
    uint32_t src = r->active ? BOOT_BLOCK1 : BOOT_BLOCK0;
    uint32_t dst = r->active ? BOOT_BLOCK0 : BOOT_BLOCK1;
    uint8_t rec[BR_SIZE];
    uint8_t buf[256];
    uint32_t off;
    int rc;

    hal_log_hex("bootrec: writing block", dst);
    hal_log_hex("bootrec: new seq", newseq);
    rc = write_result(flash_erase_sector(dst), "bootrec: erase failed");
    if (rc)
        return rc;
    /* 0x400-0xFFFF of the active block, unchanged. */
    for (off = BR_COPY_START; off < FLASH_SECTOR_SIZE; off += sizeof buf) {
        flash_read(src + off, buf, sizeof buf);
        rc = write_result(flash_program(dst + off, buf, sizeof buf),
                          "bootrec: copy failed");
        if (rc)
            return rc;
    }
    /* The record: as found, new sequence number and complement, the
       halfword pairs as the installers write them, and the type 2 slot
       blank or restored. */
    memcpy(rec, r->record, BR_SIZE);
    put_be32(rec + BR_SEQ, newseq);
    put_be32(rec + BR_SEQ_CHECK, ~newseq);
    memcpy(rec + BR_PAIRS, BR_PAIRS_VALUE, sizeof BR_PAIRS_VALUE);
    if (with_slot)
        memcpy(rec + BR_SLOT_TYPE2, r->slot2, BR_SLOT_SIZE);
    else
        memset(rec + BR_SLOT_TYPE2, 0xFF, BR_SLOT_SIZE);
    rc = write_result(flash_program(dst + 1, rec + 1, BR_SIZE - 1),
                      "bootrec: record failed");
    if (rc)
        return rc;
    rc = write_result(flash_program(dst, rec, 1),
                      "bootrec: record first byte failed");
    if (rc)
        return rc;
    /* Read it all back once more. */
    for (off = BR_COPY_START; off < FLASH_SECTOR_SIZE; off += sizeof buf) {
        uint8_t back[256];
        flash_read(src + off, buf, sizeof buf);
        flash_read(dst + off, back, sizeof buf);
        if (memcmp(buf, back, sizeof buf) != 0) {
            hal_log_hex("bootrec: copy verify failed at", dst + off);
            return (int)FLASH_PROGRAM_FAILED;
        }
    }
    flash_read(dst, buf, BR_SIZE);
    if (memcmp(buf, rec, BR_SIZE) != 0) {
        hal_log("bootrec: record verify failed");
        return (int)FLASH_PROGRAM_FAILED;
    }
    r->active = r->active ? 0 : 1;
    r->seq = newseq;
    memcpy(r->record, rec, BR_SIZE);
    hal_log_hex("bootrec: written, active block now", (uint32_t)r->active);
    return 0;
}

enum deadman_state deadman_arm(struct bootrec *r)
{
    uint32_t slot_addr;

    if (flash_identify() != FLASH_OK) {
        hal_log("deadman: flash not identified; leaving flash alone");
        return DEADMAN_NO_FLASH;
    }
    if (!bootrec_find_active(r)) {
        hal_log("deadman: no boot record; leaving flash alone");
        return DEADMAN_NO_RECORD;
    }
    if (!bootrec_slot_usable(r->slot2)) {
        hal_log("deadman: type 2 slot unused; leaving flash alone");
        return DEADMAN_NOT_OURS;
    }
    /* The net writes seq + 1 and then seq + 2, and each must beat the
       record before it in the selector's unsigned compare (§5). */
    if (r->seq >= 0xFFFFFFFEu) {
        hal_log("deadman: sequence number would wrap; leaving flash alone");
        return DEADMAN_SEQ_WRAP;
    }
    slot_addr = be32(r->slot2 + BR_SLOT_ADDR);
    hal_log_hex("deadman: type 2 slot points at", slot_addr);
    if (!bootrec_section_is_this_program(slot_addr)) {
        hal_log("deadman: that section is not this program; leaving "
                "flash alone");
        return DEADMAN_NOT_OURS;
    }
    hal_log("deadman: the slot loads this program; arming");
    if (bootrec_write(r, r->seq + 1, 0) != 0)
        return DEADMAN_FAILED;
    hal_log("deadman: armed (a reset now starts section B)");
    return DEADMAN_ARMED;
}

enum deadman_state deadman_restore(struct bootrec *r)
{
    if (bootrec_write(r, r->seq + 1, 1) != 0)
        return DEADMAN_FAILED;
    hal_log("deadman: restored (a reset now starts this program)");
    return DEADMAN_RESTORED;
}
