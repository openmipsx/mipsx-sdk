/* ELF32 big-endian loader for the MIPS-X simulator (abi §11).
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mipsx.h"

#define PT_LOAD 1
#define SHT_SYMTAB 2
#define STT_SECTION 3
#define STT_FILE 4

static uint32_t be32(const uint8_t *p) {
  return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 |
         p[3];
}
static uint16_t be16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }

static int symcmp(const void *a, const void *b) {
  const struct symbol *x = a, *y = b;
  return x->addr < y->addr ? -1 : x->addr > y->addr;
}

static int fail(const char *path, const char *msg) {
  fprintf(stderr, "mipsx-sim: error: %s: %s\n", path, msg);
  return -1;
}

static void load_symbols(const uint8_t *f, size_t size, struct program *prog) {
  uint32_t shoff = be32(f + 32);
  uint16_t shentsize = be16(f + 46), shnum = be16(f + 48);
  if (!shoff || shentsize < 40 || shoff + (uint64_t)shnum * shentsize > size)
    return;
  for (unsigned i = 0; i < shnum; i++) {
    const uint8_t *sh = f + shoff + (size_t)i * shentsize;
    if (be32(sh + 4) != SHT_SYMTAB)
      continue;
    uint32_t off = be32(sh + 16), sz = be32(sh + 20), link = be32(sh + 24);
    uint32_t entsize = be32(sh + 36);
    if (link >= shnum || entsize < 16 || off + (uint64_t)sz > size)
      return;
    const uint8_t *strsh = f + shoff + (size_t)link * shentsize;
    uint32_t stroff = be32(strsh + 16), strsz = be32(strsh + 20);
    if (stroff + (uint64_t)strsz > size || strsz == 0)
      return;
    prog->strtab = malloc(strsz + 1);
    if (!prog->strtab)
      return;
    memcpy(prog->strtab, f + stroff, strsz);
    prog->strtab[strsz] = 0;
    size_t n = sz / entsize;
    prog->syms = calloc(n ? n : 1, sizeof *prog->syms);
    if (!prog->syms)
      return;
    for (size_t k = 0; k < n; k++) {
      const uint8_t *s = f + off + k * entsize;
      uint32_t name = be32(s), value = be32(s + 4);
      unsigned type = s[12] & 0xF;
      uint16_t shndx = be16(s + 14);
      if (!name || name >= strsz || shndx == 0 || type == STT_SECTION ||
          type == STT_FILE)
        continue;
      if (prog->strtab[name] == '$')
        continue; /* mapping symbols */
      prog->syms[prog->nsyms].addr = value;
      prog->syms[prog->nsyms].name = prog->strtab + name;
      prog->nsyms++;
    }
    qsort(prog->syms, prog->nsyms, sizeof *prog->syms, symcmp);
    return;
  }
}

const struct symbol *elf_symbolize(const struct program *prog, uint32_t addr) {
  size_t lo = 0, hi = prog->nsyms;
  const struct symbol *best = NULL;
  while (lo < hi) {
    size_t mid = (lo + hi) / 2;
    if (prog->syms[mid].addr <= addr) {
      best = &prog->syms[mid];
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return best;
}

int elf_load(const char *path, uint8_t *mem, uint32_t memsize,
             struct program *prog) {
  memset(prog, 0, sizeof *prog);
  FILE *fp = fopen(path, "rb");
  if (!fp) {
    fprintf(stderr, "mipsx-sim: error: %s: %s\n", path, strerror(errno));
    return -1;
  }
  if (fseek(fp, 0, SEEK_END) != 0) {
    fclose(fp);
    return fail(path, "cannot seek");
  }
  long lsize = ftell(fp);
  rewind(fp);
  if (lsize < 52) {
    fclose(fp);
    return fail(path, "not an ELF file (too short)");
  }
  size_t size = (size_t)lsize;
  uint8_t *f = malloc(size);
  if (!f || fread(f, 1, size, fp) != size) {
    fclose(fp);
    free(f);
    return fail(path, "cannot read file");
  }
  fclose(fp);

  int rc = -1;
  if (memcmp(f, "\177ELF", 4) != 0) {
    fail(path, "not an ELF file");
    goto out;
  }
  if (f[4] != 1) {
    fail(path, "not a 32-bit ELF file (EI_CLASS must be ELFCLASS32)");
    goto out;
  }
  if (f[5] != 2) {
    fail(path, "not a big-endian ELF file (EI_DATA must be ELFDATA2MSB, "
               "abi §11.1)");
    goto out;
  }
  if (be16(f + 18) != EM_MIPS_X) {
    char msg[96];
    snprintf(msg, sizeof msg, "e_machine is %u, not EM_MIPS_X (51)",
             be16(f + 18));
    fail(path, msg);
    goto out;
  }
  if (be16(f + 16) != 2) {
    fail(path, "not an executable (e_type must be ET_EXEC; link it first)");
    goto out;
  }
  prog->entry = be32(f + 24);
  prog->flags = be32(f + 36);
  if (prog->flags & ~(EF_MIPSX_ES3890 | EF_MIPSX_VSHIFT)) {
    char msg[96];
    snprintf(msg, sizeof msg, "reserved e_flags bits set (0x%08x)",
             prog->flags);
    fail(path, msg);
    goto out;
  }
  if (prog->flags & EF_MIPSX_VSHIFT) {
    fail(path, "EF_MIPSX_VSHIFT is set, but the variable shift is not "
               "supported (plan L2)");
    goto out;
  }
  if (prog->entry & 3) {
    fail(path, "entry point is not a multiple of 4");
    goto out;
  }

  uint32_t phoff = be32(f + 28);
  uint16_t phentsize = be16(f + 42), phnum = be16(f + 44);
  if (phnum == 0 || phentsize < 32 ||
      phoff + (uint64_t)phnum * phentsize > size) {
    fail(path, "missing or truncated program headers");
    goto out;
  }
  for (unsigned i = 0; i < phnum; i++) {
    const uint8_t *ph = f + phoff + (size_t)i * phentsize;
    if (be32(ph) != PT_LOAD)
      continue;
    uint32_t off = be32(ph + 4), paddr = be32(ph + 12);
    uint32_t filesz = be32(ph + 16), memsz = be32(ph + 20);
    if (off + (uint64_t)filesz > size || filesz > memsz) {
      fail(path, "malformed PT_LOAD segment");
      goto out;
    }
    /* Load at the physical (load) address, like the device's loader. */
    if (paddr + (uint64_t)memsz > memsize) {
      char msg[160];
      snprintf(msg, sizeof msg,
               "segment 0x%08x-0x%08x does not fit in simulated RAM "
               "(0x0-0x%08x; see --mem-size)",
               paddr, paddr + memsz, memsize);
      fail(path, msg);
      goto out;
    }
    if (prog->nsegs < MAX_SEGMENTS) {
      struct segment *sg = &prog->segs[prog->nsegs++];
      sg->addr = paddr;
      sg->size = memsz;
      sg->exec = (be32(ph + 24) & 1) != 0;
    }
    memcpy(mem + paddr, f + off, filesz);
    memset(mem + paddr + filesz, 0, memsz - filesz);
  }
  load_symbols(f, size, prog);
  rc = 0;
out:
  free(f);
  return rc;
}
