/* sim/model.c: a peripheral model for running the blink example on
 * mipsx-sim, which has no peripherals of its own.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Linked into the BLINK_SIM build in place of the volatile accesses of
 * hal.h.  It models, from the same specifications and datasheet as the
 * program itself:
 *
 *   - the timer count (peripherals.md §4): advances 1 ms per read;
 *   - the system-control device (§3) with port 0 (§6): logs register
 *     writes and LED changes;
 *   - the Am29LV081B (datasheet Table 4, Table 5): unlock sequences,
 *     autoselect, byte program (1 -> 0 only), sector erase, Data# Polling
 *     with DQ7, DQ6 toggling and DQ5 on failure; 1 MB of contents in RAM
 *     with a boot record pair and a copy of this program as the section
 *     the type 2 slot points at, laid out as tools/mipsx_pack.py lays a
 *     section out (format spec §4).
 *
 * Options (the program's command line): --stuck-timer, --no-record,
 * --block1-erased, --tie, --slot-unused, --not-ours, --bad-id,
 * --erase-fail, --program-fail.  At exit the model prints what the two
 * boot-record blocks hold and whether the copied area survived, so
 * tests/test_blink.py can check the net without reading flash itself.
 *
 * Output goes straight to the simulator's I/O page (abi §13.5), not
 * through the C library, so that no .data of the C library is written
 * before the program compares its flash copy with RAM (bootrec.c).
 * All of the model's own state is in .bss for the same reason.
 */
#include <stdint.h>
#include "../board.h"
#include "../hal.h"

extern char __text_start[], __data_end[];

#define SIM_STDOUT ((volatile uint8_t *)0xFFFF0000u)
#define SIM_EXIT   ((volatile uint32_t *)0xFFFF0004u)

/* ---- options and time -------------------------------------------- */

static int opt_stuck_timer, opt_no_record, opt_block1_erased, opt_tie;
static int opt_slot_unused, opt_not_ours, opt_bad_id, opt_erase_fail;
static int opt_program_fail;

static uint32_t sim_cycles;          /* the timer count */
#define TICK_PER_READ (CPU_HZ / 1000u)

static void put(const char *s)
{
    while (*s)
        *SIM_STDOUT = (uint8_t)*s++;
}

static void put_hex(uint32_t v)
{
    static const char digits[] = "0123456789abcdef";   /* .rodata */
    char buf[11];
    int i;
    buf[0] = '0';
    buf[1] = 'x';
    for (i = 0; i < 8; i++)
        buf[2 + i] = digits[(v >> (28 - 4 * i)) & 0xF];
    buf[10] = 0;
    put(buf);
}

static void put_dec(uint32_t v)
{
    char buf[11];
    int i = 10;
    buf[i] = 0;
    do {
        buf[--i] = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    put(buf + i);
}

static void stamp(void)
{
    put("[t=");
    put_dec(sim_cycles / TICK_PER_READ);
    put("ms] ");
}

void hal_log(const char *text)
{
    stamp();
    put(text);
    put("\n");
}

void hal_log_hex(const char *text, uint32_t value)
{
    stamp();
    put(text);
    put(" ");
    put_hex(value);
    put("\n");
}

void hal_delay_loop_hint(void)
{
    sim_cycles += 1;
}

/* ---- PSW ------------------------------------------------------------ */

uint32_t hal_psw_read(void)
{
    uint32_t v;
    __asm__ volatile("movfrs psw,%0" : "=r"(v));
    return v;
}

void hal_psw_write(uint32_t psw)
{
    __asm__ volatile("movtos %0,psw" : : "r"(psw));
}

/* ---- on-chip registers ----------------------------------------------- */

static uint32_t regs[0x10000 / 4];
static uint32_t wd_kicks, wd_level;

uint32_t hal_reg_read(uint32_t off)
{
    if (off == REG_TIMER_COUNT) {
        if (!opt_stuck_timer)
            sim_cycles += TICK_PER_READ;
        return sim_cycles;
    }
    return regs[(off & 0xFFFF) / 4];
}

void hal_reg_write(uint32_t off, uint32_t value)
{
    if (off == REG_TIMER_COUNT)
        sim_cycles = value;
    if (off == REG_GPIO_WD) {
        uint32_t bit = value & 4;
        if (bit && !wd_level) {
            wd_kicks++;
            if (wd_kicks <= 3 || (wd_kicks % 50) == 0) {
                stamp();
                put("watchdog: kick ");
                put_dec(wd_kicks);
                put("\n");
            }
        }
        wd_level = bit;
    }
    regs[(off & 0xFFFF) / 4] = value;
}

/* ---- system-control device ------------------------------------------- */

static uint8_t sc_regs[128];
static int sc_phase, sc_reg, sc_is_read;
static int led_state = -1;

static void led_update(void)
{
    uint8_t data = sc_regs[SC_PORT0_DATA], dir = sc_regs[SC_PORT0_DIR];
    int on;
    if (!(dir & PORT0_LED_BIT))
        on = 0;                           /* released: Q21 off, LEDs off */
    else
        on = !(data & PORT0_LED_BIT);     /* driven 0 = on (§6) */
    if (on != led_state) {
        led_state = on;
        stamp();
        put(on ? "led: on\n" : "led: off\n");
    }
}

void hal_sc_write(uint8_t byte)
{
    if (sc_phase == 0) {
        sc_reg = byte >> 1;
        sc_is_read = byte & 1;
        sc_phase = 1;
        return;
    }
    sc_phase = 0;
    if (sc_is_read) {
        put("sysctl: data written after a read address byte\n");
        return;
    }
    sc_regs[sc_reg] = byte;
    stamp();
    put("sysctl: reg ");
    put_hex((uint32_t)sc_reg);
    put(" = ");
    put_hex(byte);
    put("\n");
    if (sc_reg == SC_PORT0_DATA || sc_reg == SC_PORT0_DIR)
        led_update();
}

uint8_t hal_sc_read(void)
{
    if (sc_phase != 1 || !sc_is_read) {
        put("sysctl: read without a read address byte\n");
        sc_phase = 0;
        return 0xFF;
    }
    sc_phase = 0;
    return sc_regs[sc_reg];
}

/* ---- Am29LV081B ------------------------------------------------------ */

static uint8_t flash[FLASH_SIZE];
static uint8_t orig_area[FLASH_SECTOR_SIZE - BR_COPY_START];  /* active */
static uint8_t orig_record[BR_SIZE];
static uint8_t start_area[2][FLASH_SECTOR_SIZE - BR_COPY_START];
static uint8_t start_record[2][BR_SIZE];

enum { F_READ, F_UNLOCK1, F_UNLOCK2, F_PROGRAM, F_ERASE1, F_ERASE2,
       F_ERASE3, F_AUTOSELECT, F_BUSY_PROGRAM, F_BUSY_ERASE };
static int fstate;
static uint32_t busy_addr, busy_polls;
static uint8_t busy_data, toggle;
static uint32_t erases, programs;

#define PROGRAM_POLLS 3
#define ERASE_POLLS   40

uint8_t hal_flash_read(uint32_t off)
{
    off &= FLASH_SIZE - 1;
    switch (fstate) {
    case F_AUTOSELECT:
        /* Table 4: X00 manufacturer, X01 device. */
        if ((off & 0xFF) == 0)
            return opt_bad_id ? 0x7F : FLASH_MFR_ID;
        if ((off & 0xFF) == 1)
            return opt_bad_id ? 0x7F : FLASH_DEV_ID;
        return 0;
    case F_BUSY_PROGRAM:
        if (busy_polls == 0 || opt_program_fail) {
            /* Table 5: DQ7 = complement of the datum, DQ6 toggles;
               DQ5 set once the timing limit is exceeded. */
            toggle ^= 0x40;
            return (uint8_t)((~busy_data & 0x80) | toggle |
                             (opt_program_fail ? 0x20 : 0));
        }
        busy_polls--;
        if (busy_polls == 0) {
            fstate = F_READ;
            return flash[off];
        }
        toggle ^= 0x40;
        return (uint8_t)((~busy_data & 0x80) | toggle);
    case F_BUSY_ERASE:
        if (opt_erase_fail) {
            toggle ^= 0x40;
            return (uint8_t)(0x20 | toggle);  /* DQ7 = 0, DQ5 = 1 */
        }
        busy_polls--;
        if (busy_polls == 0) {
            uint32_t i, base = busy_addr & ~(FLASH_SECTOR_SIZE - 1);
            for (i = 0; i < FLASH_SECTOR_SIZE; i++)
                flash[base + i] = 0xFF;
            fstate = F_READ;
            return flash[off];
        }
        toggle ^= 0x40;
        return toggle;                        /* DQ7 = 0 while erasing */
    default:
        return flash[off];
    }
}

void hal_flash_write(uint32_t off, uint8_t value)
{
    off &= FLASH_SIZE - 1;
    if (fstate == F_BUSY_PROGRAM || fstate == F_BUSY_ERASE) {
        /* "Any commands written to the device during the Embedded
           Program Algorithm are ignored", likewise for erase; except
           that the reset command recovers from a DQ5 failure. */
        if (value == 0xF0 && (opt_erase_fail || opt_program_fail))
            fstate = F_READ;
        return;
    }
    /* F0 is the reset command "between the sequence cycles" (datasheet,
       "Reset Command"); the fourth cycle of a program sequence is data,
       so a byte of 0xF0 is programmed, not a reset. */
    if (value == 0xF0 && fstate != F_PROGRAM) {
        fstate = F_READ;
        return;
    }
    switch (fstate) {
    case F_READ:
        fstate = (off == 0x555 && value == 0xAA) ? F_UNLOCK1 : F_READ;
        break;
    case F_UNLOCK1:
        fstate = (off == 0x2AA && value == 0x55) ? F_UNLOCK2 : F_READ;
        break;
    case F_UNLOCK2:
        if (off != 0x555) {
            fstate = F_READ;
        } else if (value == 0x90) {
            fstate = F_AUTOSELECT;
        } else if (value == 0xA0) {
            fstate = F_PROGRAM;
        } else if (value == 0x80) {
            fstate = F_ERASE1;
        } else {
            fstate = F_READ;
        }
        break;
    case F_PROGRAM:
        /* Only 1 -> 0 transitions happen (datasheet, "Byte Program
           Command Sequence"). */
        flash[off] &= value;
        busy_addr = off;
        busy_data = value;
        busy_polls = PROGRAM_POLLS;
        programs++;
        fstate = F_BUSY_PROGRAM;
        break;
    case F_ERASE1:
        fstate = (off == 0x555 && value == 0xAA) ? F_ERASE2 : F_READ;
        break;
    case F_ERASE2:
        fstate = (off == 0x2AA && value == 0x55) ? F_ERASE3 : F_READ;
        break;
    case F_ERASE3:
        if (value == 0x30) {
            busy_addr = off;
            busy_polls = ERASE_POLLS;
            erases++;
            stamp();
            put("flash: erase sector ");
            put_hex(off & ~(FLASH_SECTOR_SIZE - 1));
            put("\n");
            fstate = F_BUSY_ERASE;
        } else {
            fstate = F_READ;
        }
        break;
    case F_AUTOSELECT:
        break;                                /* only F0 leaves it */
    default:
        fstate = F_READ;
        break;
    }
}

/* ---- initial flash contents -------------------------------------------- */

static void w32(uint32_t off, uint32_t v)
{
    flash[off] = (uint8_t)(v >> 24);
    flash[off + 1] = (uint8_t)(v >> 16);
    flash[off + 2] = (uint8_t)(v >> 8);
    flash[off + 3] = (uint8_t)v;
}

static void write_record(uint32_t block, uint32_t seq, uint32_t slot1,
                         uint32_t slot2)
{
    static const char magic[8] = {'S', 'I', 'P', 'U', 'R', 'A', ' ', '*'};
    uint32_t i;
    for (i = 0; i < 8; i++)
        flash[block + i] = (uint8_t)magic[i];
    w32(block + BR_SEQ, seq);
    w32(block + BR_SEQ_CHECK, ~seq);
    /* §5: halfwords 0x0400 and 0x1000, each with its complement. */
    flash[block + 0x10] = 0x04; flash[block + 0x11] = 0x00;
    flash[block + 0x12] = 0xFB; flash[block + 0x13] = 0xFF;
    flash[block + 0x14] = 0x10; flash[block + 0x15] = 0x00;
    flash[block + 0x16] = 0xEF; flash[block + 0x17] = 0xFF;
    for (i = 0; i < 8; i++) {
        flash[block + BR_SLOT_TYPE1 + i] = (uint8_t)magic[i];
        if (slot2)
            flash[block + BR_SLOT_TYPE2 + i] = (uint8_t)magic[i];
    }
    w32(block + BR_SLOT_TYPE1 + BR_SLOT_ADDR, slot1);
    w32(block + BR_SLOT_TYPE1 + BR_SLOT_CHECK, ~slot1);
    if (slot2) {
        w32(block + BR_SLOT_TYPE2 + BR_SLOT_ADDR, slot2);
        w32(block + BR_SLOT_TYPE2 + BR_SLOT_CHECK, ~slot2);
    }
}

static void fill_block_area(uint32_t block, uint8_t seed)
{
    uint32_t i;
    /* A header copy at 0x400 (magic then a version string), a few event
       log entries from 0xFC0 downwards, some configuration records and
       their mirror; the rest erased. */
    static const char hdr[] = "SpA3000 FiRmWaRe";
    for (i = 0; i < 16; i++)
        flash[block + 0x400 + i] = (uint8_t)hdr[i];
    for (i = 0; i < 8; i++)
        flash[block + 0x400 + 0x5C + i] = (uint8_t)"9.0.0(x)"[i];
    for (i = 0; i < 3; i++) {
        uint32_t slot = block + 0xFC0 - 0x40 * i;
        w32(slot, i + 1);
        flash[slot + 4] = (uint8_t)('A' + i);
        flash[slot + 5] = seed;
    }
    for (i = 0; i < 0x300; i++) {
        flash[block + 0x1000 + i] = (uint8_t)(seed ^ (i * 7));
        flash[block + 0x8800 + i] = (uint8_t)(seed ^ (i * 7));
    }
}

#define SECTION_ENTRY 0x50000u

static void install_program(uint32_t entry)
{
    uint32_t body = (uint32_t)(__data_end - __text_start);
    uint32_t data = entry + ENTRY_SIZE, header = data, i;
    uint32_t dir_off, length;

    body = (body + 3) & ~3u;
    dir_off = 0x24 + body;
    length = dir_off + 2 * DIR_RECORD_SIZE + 0x10;
    /* Table entry (§3): type 2, data at +0x80, length. */
    flash[entry + ENTRY_TYPE] = 2;
    w32(entry + ENTRY_DATA_OFFSET, ENTRY_SIZE);
    w32(entry + ENTRY_LENGTH, length);
    /* Packed header (§4.1), empty chunk list, the body, the directory
       (§4.4): one copy record and the entry record. */
    w32(header + 0x00, PACKED_MAGIC);
    w32(header + 0x04, dir_off);
    w32(header + 0x08, 2);
    w32(header + 0x0C, 0x1FFFF0);
    w32(header + 0x10, length);
    w32(header + 0x14, length - 0x10);
    w32(header + 0x20, 0);
    for (i = 0; i < body; i++)
        flash[header + 0x24 + i] = (uint8_t)__text_start[i];
    if (opt_not_ours)
        flash[header + 0x24 + body / 2] ^= 0x55;
    w32(header + dir_off + 0, DIR_COPY);
    w32(header + dir_off + 4, 0x24);
    w32(header + dir_off + 8, (uint32_t)__text_start);
    w32(header + dir_off + 12, body / 4);
    w32(header + dir_off + 16, 1);
    w32(header + dir_off + 20, 0x03);
    w32(header + dir_off + 24, 0x40000000 | ((uint32_t)__text_start >> 2));
}

static int streq(const char *a, const char *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a == *b;
}

void sim_model_init(int argc, char **argv)
{
    uint32_t i;
    int k;

    for (k = 1; k < argc; k++) {
        const char *a = argv[k];
        if (streq(a, "--stuck-timer")) opt_stuck_timer = 1;
        else if (streq(a, "--no-record")) opt_no_record = 1;
        else if (streq(a, "--block1-erased")) opt_block1_erased = 1;
        else if (streq(a, "--tie")) opt_tie = 1;
        else if (streq(a, "--slot-unused")) opt_slot_unused = 1;
        else if (streq(a, "--not-ours")) opt_not_ours = 1;
        else if (streq(a, "--bad-id")) opt_bad_id = 1;
        else if (streq(a, "--erase-fail")) opt_erase_fail = 1;
        else if (streq(a, "--program-fail")) opt_program_fail = 1;
        else {
            put("model: unknown option ");
            put(a);
            put("\n");
            *SIM_EXIT = 2;
        }
    }
    for (i = 0; i < FLASH_SIZE; i++)
        flash[i] = 0xFF;
    install_program(SECTION_ENTRY);
    if (!opt_no_record) {
        uint32_t slot2 = opt_slot_unused ? 0 : FLASH_RECORD_BASE + SECTION_ENTRY;
        write_record(BOOT_BLOCK0, 5, FLASH_RECORD_BASE + 0x20000, slot2);
        fill_block_area(BOOT_BLOCK0, 0x11);
        if (!opt_block1_erased) {
            write_record(BOOT_BLOCK1, opt_tie ? 5 : 4,
                         FLASH_RECORD_BASE + 0x20000, slot2);
            fill_block_area(BOOT_BLOCK1, opt_tie ? 0x11 : 0x22);
        }
    }
    /* What the active block holds now, for the checks at exit.  With a
       tie, block 1 is the active one (as sections A and B choose). */
    {
        uint32_t active = (opt_tie && !opt_block1_erased) ? BOOT_BLOCK1
                                                          : BOOT_BLOCK0;
        for (i = 0; i < sizeof orig_area; i++)
            orig_area[i] = flash[active + BR_COPY_START + i];
        for (i = 0; i < BR_SIZE; i++)
            orig_record[i] = flash[active + i];
        for (i = 0; i < sizeof start_area[0]; i++) {
            start_area[0][i] = flash[BOOT_BLOCK0 + BR_COPY_START + i];
            start_area[1][i] = flash[BOOT_BLOCK1 + BR_COPY_START + i];
        }
        for (i = 0; i < BR_SIZE; i++) {
            start_record[0][i] = flash[BOOT_BLOCK0 + i];
            start_record[1][i] = flash[BOOT_BLOCK1 + i];
        }
    }
    put("model: ready\n");
}

static void dump_record(uint32_t block)
{
    uint32_t i;
    put("record ");
    put_hex(block);
    put(":");
    for (i = 0; i < BR_SIZE; i++) {
        char h[3];
        h[0] = "0123456789abcdef"[flash[block + i] >> 4];
        h[1] = "0123456789abcdef"[flash[block + i] & 0xF];
        h[2] = 0;
        if ((i & 0xF) == 0)
            put(" ");
        put(h);
    }
    put("\n");
}

static int area_equals(uint32_t block, const uint8_t *want)
{
    uint32_t i;
    for (i = 0; i < sizeof orig_area; i++)
        if (flash[block + BR_COPY_START + i] != want[i])
            return 0;
    return 1;
}

static int record_unchanged(uint32_t block, const uint8_t *want)
{
    uint32_t i;
    for (i = 0; i < BR_SIZE; i++)
        if (flash[block + i] != want[i])
            return 0;
    return 1;
}

static int record_equals_original_except(uint32_t block, int slot_blank)
{
    uint32_t i;
    for (i = 0; i < BR_SIZE; i++) {
        if (i >= BR_SEQ && i < BR_SEQ_CHECK + 4)
            continue;
        if (i >= BR_SLOT_TYPE2 && i < BR_SLOT_TYPE2 + BR_SLOT_SIZE) {
            uint8_t want = slot_blank ? 0xFF : orig_record[i];
            if (flash[block + i] != want)
                return 0;
            continue;
        }
        if (flash[block + i] != orig_record[i])
            return 0;
    }
    return 1;
}

void sim_model_exit(int status)
{
    uint32_t b, seq0, seq1;

    put("model: erases ");
    put_dec(erases);
    put(" programs ");
    put_dec(programs);
    put(" kicks ");
    put_dec(wd_kicks);
    put("\n");
    dump_record(BOOT_BLOCK0);
    dump_record(BOOT_BLOCK1);
    seq0 = ((uint32_t)flash[BR_SEQ] << 24) | ((uint32_t)flash[BR_SEQ + 1] << 16) |
           ((uint32_t)flash[BR_SEQ + 2] << 8) | flash[BR_SEQ + 3];
    seq1 = ((uint32_t)flash[BOOT_BLOCK1 + BR_SEQ] << 24) |
           ((uint32_t)flash[BOOT_BLOCK1 + BR_SEQ + 1] << 16) |
           ((uint32_t)flash[BOOT_BLOCK1 + BR_SEQ + 2] << 8) |
           flash[BOOT_BLOCK1 + BR_SEQ + 3];
    put("check: seq0 ");
    put_dec(seq0);
    put(" seq1 ");
    put_dec(seq1);
    put("\n");
    for (b = 0; b < 2; b++) {
        uint32_t block = b ? BOOT_BLOCK1 : BOOT_BLOCK0;
        /* The area 0x400-0xFFFF: as at the start (the block was not
           touched), a copy of the active block's (it was rewritten), or
           something else.  The record likewise: as at the start, or the
           active record with the slot blank or restored and a new
           sequence number, or something else. */
        put("check: block ");
        put_dec(b);
        put(" area ");
        if (area_equals(block, start_area[b]))
            put("as-at-start");
        else if (area_equals(block, orig_area))
            put("copy-of-active");
        else
            put("OTHER");
        put(", record ");
        if (record_unchanged(block, start_record[b]))
            put("as-at-start");
        else if (record_equals_original_except(block, 1))
            put("slot-blank");
        else if (record_equals_original_except(block, 0))
            put("slot-restored");
        else
            put("OTHER");
        put("\n");
    }
    *SIM_EXIT = (uint32_t)status;
    for (;;)
        ;
}
