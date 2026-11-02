/* bootrec.h: the boot record and the dead-man net.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef BLINK_BOOTREC_H
#define BLINK_BOOTREC_H

#include <stdint.h>
#include "board.h"

struct bootrec {
    int active;              /* block holding the record in use: 0 or 1 */
    uint32_t seq;            /* its sequence number */
    uint8_t record[BR_SIZE]; /* the record as found */
    uint8_t slot2[BR_SLOT_SIZE]; /* the type 2 slot as found, for restore */
};

enum deadman_state {
    DEADMAN_IDLE = 0,
    DEADMAN_NO_FLASH,     /* the chip did not identify: nothing touched */
    DEADMAN_NO_RECORD,    /* no valid boot record: nothing touched */
    DEADMAN_NOT_OURS,     /* the type 2 slot is unused or does not load
                             this program (started by the scan?): nothing
                             touched */
    DEADMAN_SEQ_WRAP,     /* the sequence number is too close to
                             0xFFFFFFFF for two more records: nothing
                             touched */
    DEADMAN_ARMED,        /* a record without our slot is in flash */
    DEADMAN_RESTORED,     /* and a newer one with it again */
    DEADMAN_FAILED        /* a flash operation failed; see the log */
};

/* Reads both blocks and fills *R with the record the boot selector
   follows.  Returns 0 if neither holds a record (format spec §5, "What
   each program checks in a record": only the magic is checked; of two,
   the higher sequence number compared unsigned wins, block 0 on a
   tie). */
int bootrec_find_active(struct bootrec *r);

/* A slot is usable when its address is not 0xFFFFFFFF and address OR
   check is 0xFFFFFFFF (§5, "Boot record"). */
int bootrec_slot_usable(const uint8_t *slot);

/* Walks the packed section whose table entry is at flash address ADDR
   and checks that every 0x01 (copy) record's bytes in flash equal the
   bytes now in RAM at its load address: that is, that the section is a
   faithful copy of the program that is running.  Must run before any
   .data variable is written. */
int bootrec_section_is_this_program(uint32_t addr);

/* Writes a new record into the inactive block: the active block's
   0x400-0xFFFF copied unchanged, then the record with sequence number
   NEWSEQ, its complement, the installers' halfword pairs and the type 2
   slot either blanked (WITH_SLOT = 0) or restored
   from R->slot2 (WITH_SLOT = 1).  On success *R describes the new active
   record.  Returns 0 on success, else a flash_result code. */
int bootrec_write(struct bootrec *r, uint32_t newseq, int with_slot);

/* The whole dead-man sequence, first thing after the watchdog kick. */
enum deadman_state deadman_arm(struct bootrec *r);
enum deadman_state deadman_restore(struct bootrec *r);

#endif
