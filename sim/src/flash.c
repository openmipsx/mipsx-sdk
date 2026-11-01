/* SPA3000 board model: the AMD Am29LV081B flash.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * [spec: flash.md §1; hardware.md §2 U3]: 1 MB, 8-bit data bus, sixteen
 * uniform 64 KB sectors, AMD command set with unlock addresses 0x555 and
 * 0x2AA of which only A10-A0 are decoded, autoselect manufacturer 0x01
 * and device 0x38, byte program 0xA0, sector erase confirm 0x30.
 * Command details are the public Am29LV081B datasheet's Command
 * Definitions table [datasheet: Am29LV081B, "Command Definitions" and
 * "Autoselect Codes"].  Programs and erases complete at once, so the
 * datasheet's status bits (DQ7 data polling, DQ6 toggle, DQ5 timeout)
 * read as the finished data: a polling loop sees completion on its first
 * read.  Timing and the 0xF0000 identity sector's protection are not
 * modelled.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "board.h"

int flash_init(struct board *b, const char *path) {
  struct flash *f = &b->flash;
  memset(f, 0, sizeof *f);
  f->data = malloc(FLASH_SIZE);
  if (!f->data) {
    fprintf(stderr, "mipsx-sim: error: out of memory\n");
    return -1;
  }
  memset(f->data, 0xFF, FLASH_SIZE); /* erased */
  if (!path)
    return 0;
  FILE *fp = fopen(path, "rb");
  if (!fp) {
    fprintf(stderr, "mipsx-sim: error: %s: %s\n", path, strerror(errno));
    return -1;
  }
  size_t n = fread(f->data, 1, FLASH_SIZE, fp);
  int extra = fgetc(fp) != EOF;
  fclose(fp);
  if (extra) {
    fprintf(stderr, "mipsx-sim: error: %s: flash image is larger than the "
            "%u-byte part\n", path, FLASH_SIZE);
    return -1;
  }
  (void)n;
  return 0;
}

/* Reads assemble bytes big-endian, as the bus controller must to run the
 * boot code from flash [spec: firmware-image-format.md: the boot section
 * runs from flash; peripherals.md §1]. */
uint32_t flash_read(struct board *b, uint32_t off, unsigned size) {
  struct flash *f = &b->flash;
  uint32_t v = 0;
  for (unsigned i = 0; i < size; i++) {
    uint32_t a = (off + i) & (FLASH_SIZE - 1);
    uint8_t byte;
    if (f->state == FL_AUTOSELECT) {
      /* [datasheet: Autoselect Codes; spec: flash.md §1]: A7-A0 = 0x00
       * manufacturer, 0x01 device, 0x02 sector protection (0: none, as
       * the part has no software protection). */
      switch (a & 0xFF) {
      case 0x00: byte = FLASH_MFR_ID; break;
      case 0x01: byte = FLASH_DEV_ID; break;
      default: byte = 0x00; break;
      }
    } else {
      byte = f->data[a];
    }
    v = v << 8 | byte;
  }
  return v;
}

static void erase_sector(struct board *b, uint32_t off) {
  struct flash *f = &b->flash;
  uint32_t s = off & ~(FLASH_SECTOR - 1);
  memset(f->data + s, 0xFF, FLASH_SECTOR);
  f->erases++;
  board_logf(b, "flash sector 0x%05x erased", s);
}

/* Writes are commands [datasheet: Command Definitions].  The bus is 8 bits
 * wide, so a wider store delivers its low byte at the given address
 * (modelling choice; the firmware uses byte stores, flash.md §1). */
void flash_write(struct board *b, uint32_t off, unsigned size, uint32_t v) {
  struct flash *f = &b->flash;
  uint32_t a11 = off & 0x7FF; /* only A10-A0 are decoded for unlock */
  uint8_t d = (uint8_t)v;
  (void)size;

  if (f->state == FL_PROGRAM) {
    /* The datasheet's program can only clear bits: programming a 1 over a
     * 0 leaves the 0 [datasheet: Byte Program Command Sequence]. */
    f->data[off] &= d;
    f->programs++;
    f->state = FL_READ;
    return;
  }
  if (d == 0xF0) {
    /* Reset to read array from any state but the program data cycle
     * [datasheet: Reset Command]. */
    f->state = FL_READ;
    return;
  }
  switch (f->state) {
  case FL_READ:
    if (a11 == 0x555 && d == 0xAA)
      f->state = FL_UNLOCK1;
    break;
  case FL_UNLOCK1:
    f->state = (a11 == 0x2AA && d == 0x55) ? FL_UNLOCK2 : FL_READ;
    break;
  case FL_UNLOCK2:
    if (a11 != 0x555) {
      f->state = FL_READ;
    } else if (d == 0x90) {
      f->state = FL_AUTOSELECT;
    } else if (d == 0xA0) {
      f->state = FL_PROGRAM;
    } else if (d == 0x80) {
      f->state = FL_ERASE1;
    } else {
      f->state = FL_READ; /* unlock bypass (0x20) and others: not modelled */
    }
    break;
  case FL_AUTOSELECT:
    /* Only the reset command leaves autoselect [datasheet]. */
    break;
  case FL_ERASE1:
    f->state = (a11 == 0x555 && d == 0xAA) ? FL_ERASE2 : FL_READ;
    break;
  case FL_ERASE2:
    f->state = (a11 == 0x2AA && d == 0x55) ? FL_ERASE3 : FL_READ;
    break;
  case FL_ERASE3:
    if (d == 0x30) {
      erase_sector(b, off); /* sector address from the sixth cycle */
    } else if (d == 0x10 && a11 == 0x555) {
      memset(f->data, 0xFF, FLASH_SIZE); /* chip erase */
      f->erases++;
      board_logf(b, "flash chip erased");
    }
    f->state = FL_READ;
    break;
  default:
    f->state = FL_READ;
    break;
  }
}
