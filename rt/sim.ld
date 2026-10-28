/* sim.ld: linker script for programs run on mipsx-sim.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * GNU ld / lld syntax.  Implements docs/abi.md §13.1 (linker-defined
 * symbols) and §13.2 (memory map): 2 MB of RAM at 0, optional trap and
 * exception vectors from 0 (.vectors), code from 0x2000, then read-only
 * data, constructors, .data, .sdata, .sbss and .bss, and the stack at
 * the top of RAM.  The simulator loads every PT_LOAD segment at its load
 * address, so .data runs where it is loaded and crt0 does not copy it.
 *
 * Linked with ld.lld by rt/tests/test_llvm.py (make check-llvm), which
 * checks the result against sim/tests/mxasm.py's link_layout().  The other
 * rt/ tests use link_layout() in place of the linker; keep the two in step.
 *
 * Use: ld.lld -T sim.ld crt0.o exit-sim.o prog.o -o prog
 */

ENTRY(_start)

MEMORY
{
  RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 0x200000
}

SECTIONS
{
  /* Exception entry is address 0 (which must hold a nop) and trap n
     enters at byte n * 32 (abi §13.2).  Empty unless a program has
     .vectors input sections; then 0x0000-0x1FFF is theirs. */
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

  /* abi §5.2: cb0 covers the first 512 KB of .text, cb1 the next. */
  __mipsx_cb0 = __text_start + 0x40000;
  __mipsx_cb1 = __mipsx_cb0 + 0x80000;
  /* abi §6.3: start of .sdata + 64 KB, or of .data if .sdata is empty. */
  _gp = (SIZEOF(.sdata) > 0 ? __sdata_start : __data_start) + 0x10000;
  /* Top of RAM, 8-byte aligned; the simulator's reset sp is the same. */
  __stack_top = ORIGIN(RAM) + LENGTH(RAM) - 16;

  ASSERT(_end <= __stack_top - 0x10000,
         "sim.ld: program leaves less than 64 KB of RAM for the stack")

  /* Debug sections keep their default placement (not allocated). */
  /DISCARD/ : { *(.note.GNU-stack) *(.comment) }
}
