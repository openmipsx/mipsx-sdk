/* device.ld: linker script for programs on the SPA3000 (ES3890).
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * GNU ld / lld syntax.  Implements docs/abi.md §13.1 and §13.2 for the
 * device: 2 MB of SDRAM at 0.  The output is turned into an upgrade image
 * by tools/mipsx-pack, whose loader stub copies every PT_LOAD segment
 * from flash to its load address in RAM and jumps to _start (tools/
 * README.md).  So, as on the simulator, everything runs where it is
 * loaded, .data needs no copy, and .bss is cleared by crt0.
 *
 * The layout is the same as sim.ld; the two differ only in the checks at
 * the end.  The stack top, 0x1FFFF0, is the value the stock images put
 * in their packed header (format spec §4.1).
 *
 * Linked with ld.lld, packed and verified by rt/tests/test_llvm.py
 * (make check-llvm).
 *
 * Use: ld.lld -T device.ld crt0.o exit-device.o prog.o -o prog
 *      mipsx-pack prog -o prog.bin --version 9.0.0
 */

ENTRY(_start)

MEMORY
{
  RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 0x200000
}

SECTIONS
{
  /* Exception entry is address 0 (which must hold a nop) and trap n
     enters at byte n * 32 (abi §13.2).  0x0000-0x1FFF is kept for
     vectors; the packer's loader stub also uses a few words there while
     it starts (tools/README.md). */
  .vectors 0x0 : { KEEP(*(.vectors)) } > RAM

  .text 0x2000 : {
    __text_start = .;
    KEEP(*(.text.start))            /* crt0's _start comes first */
    *(.text.unlikely .text.unlikely.*)
    *(.text .text.*)
    . = ALIGN(4);
    __text_end = .;
  } > RAM

  .rodata : ALIGN(8) {
    *(.rodata .rodata.*)
  } > RAM

  .init_array : ALIGN(4) {
    __init_array_start = .;
    KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
    KEEP(*(.init_array))
    __init_array_end = .;
  } > RAM

  /* Destructors, run backwards by the C library's exit.  picolibc puts
     the pointer to its atexit runner in .fini_array_onexit, which must
     come last (so it runs first). */
  .fini_array : ALIGN(4) {
    __fini_array_start = .;
    KEEP(*(SORT_BY_INIT_PRIORITY(.fini_array.*)))
    KEEP(*(.fini_array))
    KEEP(*(.fini_array*))
    __fini_array_end = .;
  } > RAM

  .data : ALIGN(8) {
    __data_start = .;
    *(.data .data.*)
    . = ALIGN(4);
  } > RAM
  __data_load = LOADADDR(.data);

  .sdata : ALIGN(4) {
    __sdata_start = .;
    *(.sdata .sdata.*)
    . = ALIGN(4);
    __data_end = .;                 /* end of .data and .sdata */
  } > RAM

  .sbss (NOLOAD) : ALIGN(8) {
    __bss_start = .;                /* start of .sbss and .bss */
    *(.sbss .sbss.* .scommon)
    . = ALIGN(4);
  } > RAM

  .bss (NOLOAD) : ALIGN(4) {
    *(.bss .bss.* COMMON)
    . = ALIGN(8);
    __bss_end = .;
  } > RAM
  _end = .;

  /* abi §5.2: cb0 covers the first 512 KB of .text, cb1 the next.  The
     packer also writes cb0 / 4 into the image's type 0x07 record, which
     then equals the first code word + 0x10000, as in the stock images
     (format spec §4.4). */
  __mipsx_cb0 = __text_start + 0x40000;
  __mipsx_cb1 = __mipsx_cb0 + 0x80000;
  /* abi §6.3: start of .sdata + 64 KB, or of .data if .sdata is empty. */
  _gp = (SIZEOF(.sdata) > 0 ? __sdata_start : __data_start) + 0x10000;
  __stack_top = 0x001FFFF0;

  /* malloc's heap (the C library's sbrk): from _end up to the 64 KB
     kept for the stack. */
  __heap_start = _end;
  __heap_end = __stack_top - 0x10000;

  ASSERT(_end <= __stack_top - 0x10000,
         "device.ld: program leaves less than 64 KB of RAM for the stack")
  /* The image's section may hold at most 0xFFFFF bytes (format spec §3);
     the loaded bytes plus the packer's header, directory and stub must
     fit.  mipsx-pack checks the exact size. */
  ASSERT(__data_end - __text_start <= 0xF0000,
         "device.ld: program too large for one image section")

  /DISCARD/ : { *(.note.GNU-stack) *(.comment) }
}
