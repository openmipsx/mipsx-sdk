/* littlefs self-test on the simulator, on littlefs's own RAM block
 * device: format, directories, files of several sizes, seek, truncate,
 * rename, remove, many rewrites of a small configuration file (block
 * compaction and wear), and a remount that checks everything again.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdio.h>
#include <string.h>

#include "lfs.h"
#include "bd/lfs_rambd.h"

#define BLOCK_SIZE 4096
#define BLOCK_COUNT 32

static unsigned char flash[BLOCK_SIZE * BLOCK_COUNT];
static unsigned char read_buf[64], prog_buf[64], look_buf[16];
static lfs_rambd_t rambd;
static const struct lfs_rambd_config rambd_cfg = {
  .read_size = 16, .prog_size = 16, .erase_size = BLOCK_SIZE,
  .erase_count = BLOCK_COUNT, .buffer = flash,
};
static const struct lfs_config cfg = {
  .context = &rambd,
  .read = lfs_rambd_read, .prog = lfs_rambd_prog,
  .erase = lfs_rambd_erase, .sync = lfs_rambd_sync,
  .read_size = 16, .prog_size = 16, .block_size = BLOCK_SIZE,
  .block_count = BLOCK_COUNT, .block_cycles = 100, .cache_size = 64,
  .lookahead_size = 16, .read_buffer = read_buf, .prog_buffer = prog_buf,
  .lookahead_buffer = look_buf,
};

static lfs_t lfs;
static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static unsigned char pattern(unsigned seed, unsigned i)
{
  unsigned x = seed * 2654435761u + i * 40503u;
  return (unsigned char)(x ^ (x >> 13));
}

static unsigned char file_buf[64];
static const struct lfs_file_config file_cfg = { .buffer = file_buf };

static void write_file(const char *path, unsigned seed, unsigned len)
{
  lfs_file_t f;
  unsigned char chunk[100];
  CHECK(lfs_file_opencfg(&lfs, &f, path, LFS_O_WRONLY | LFS_O_CREAT | LFS_O_TRUNC, &file_cfg) == 0);
  for (unsigned off = 0; off < len; off += sizeof chunk) {
    unsigned n = len - off < sizeof chunk ? len - off : sizeof chunk;
    for (unsigned i = 0; i < n; i++)
      chunk[i] = pattern(seed, off + i);
    CHECK(lfs_file_write(&lfs, &f, chunk, n) == (lfs_ssize_t)n);
  }
  CHECK(lfs_file_close(&lfs, &f) == 0);
}

static void check_file(const char *path, unsigned seed, unsigned len)
{
  lfs_file_t f;
  unsigned char chunk[77];
  unsigned bad = 0;
  CHECK(lfs_file_opencfg(&lfs, &f, path, LFS_O_RDONLY, &file_cfg) == 0);
  CHECK(lfs_file_size(&lfs, &f) == (lfs_soff_t)len);
  for (unsigned off = 0; off < len; off += sizeof chunk) {
    unsigned n = len - off < sizeof chunk ? len - off : sizeof chunk;
    CHECK(lfs_file_read(&lfs, &f, chunk, n) == (lfs_ssize_t)n);
    for (unsigned i = 0; i < n; i++)
      bad += chunk[i] != pattern(seed, off + i);
  }
  CHECK(lfs_file_read(&lfs, &f, chunk, 1) == 0);
  CHECK(lfs_file_close(&lfs, &f) == 0);
  if (bad)
    printf("%s: %u bad bytes\n", path, bad);
  CHECK(bad == 0);
}

static const unsigned sizes[] = { 0, 1, 15, 16, 17, 500, 4095, 4096, 4097, 20000 };
#define NSIZES (sizeof sizes / sizeof sizes[0])

static void check_all(void)
{
  char path[32];
  for (unsigned k = 0; k < NSIZES; k++) {
    sprintf(path, "data/f%u", k);
    check_file(path, k, sizes[k]);
  }
  check_file("etc/config", 999, 300);
  check_file("etc/renamed", 7, 1234);

  /* Directory listing: ".", ".." and the files. */
  lfs_dir_t d;
  struct lfs_info info;
  unsigned n = 0, files = 0;
  CHECK(lfs_dir_open(&lfs, &d, "data") == 0);
  while (lfs_dir_read(&lfs, &d, &info) > 0) {
    n++;
    files += info.type == LFS_TYPE_REG;
  }
  CHECK(lfs_dir_close(&lfs, &d) == 0);
  CHECK(n == NSIZES + 2);
  CHECK(files == NSIZES);
  CHECK(lfs_stat(&lfs, "etc/old", &info) == LFS_ERR_NOENT);
  CHECK(lfs_stat(&lfs, "gone", &info) == LFS_ERR_NOENT);
}

int main(void)
{
  char path[32];
  lfs_file_t f;
  struct lfs_info info;

  CHECK(lfs_rambd_create(&cfg, &rambd_cfg) == 0);
  CHECK(lfs_mount(&lfs, &cfg) != 0); /* blank flash */
  CHECK(lfs_format(&lfs, &cfg) == 0);
  CHECK(lfs_mount(&lfs, &cfg) == 0);

  CHECK(lfs_mkdir(&lfs, "data") == 0);
  CHECK(lfs_mkdir(&lfs, "etc") == 0);
  CHECK(lfs_mkdir(&lfs, "gone") == 0);
  CHECK(lfs_mkdir(&lfs, "data") == LFS_ERR_EXIST);
  for (unsigned k = 0; k < NSIZES; k++) {
    sprintf(path, "data/f%u", k);
    write_file(path, k, sizes[k]);
  }
  write_file("etc/old", 7, 1234);
  CHECK(lfs_rename(&lfs, "etc/old", "etc/renamed") == 0);
  CHECK(lfs_remove(&lfs, "gone") == 0);

  /* Rewrite a small file many times: forces metadata compaction and
   * block relocation (block_cycles = 100). */
  for (unsigned i = 0; i < 400; i++)
    write_file("etc/config", 1000 + i, 300);
  write_file("etc/config", 999, 300);

  /* Seek, overwrite and truncate. */
  write_file("tmp", 5, 3000);
  CHECK(lfs_file_opencfg(&lfs, &f, "tmp", LFS_O_RDWR, &file_cfg) == 0);
  CHECK(lfs_file_seek(&lfs, &f, 2000, LFS_SEEK_SET) == 2000);
  unsigned char b = 0;
  CHECK(lfs_file_read(&lfs, &f, &b, 1) == 1);
  CHECK(b == pattern(5, 2000));
  CHECK(lfs_file_seek(&lfs, &f, -1, LFS_SEEK_CUR) == 2000);
  b = 0x5a;
  CHECK(lfs_file_write(&lfs, &f, &b, 1) == 1);
  CHECK(lfs_file_truncate(&lfs, &f, 2001) == 0);
  CHECK(lfs_file_close(&lfs, &f) == 0);
  CHECK(lfs_stat(&lfs, "tmp", &info) == 0);
  CHECK(info.size == 2001);
  CHECK(lfs_file_opencfg(&lfs, &f, "tmp", LFS_O_RDONLY, &file_cfg) == 0);
  CHECK(lfs_file_seek(&lfs, &f, 2000, LFS_SEEK_SET) == 2000);
  CHECK(lfs_file_read(&lfs, &f, &b, 1) == 1);
  CHECK(b == 0x5a);
  CHECK(lfs_file_close(&lfs, &f) == 0);
  CHECK(lfs_remove(&lfs, "tmp") == 0);

  check_all();
  lfs_ssize_t used = lfs_fs_size(&lfs);
  CHECK(used > 0 && used < BLOCK_COUNT);
  CHECK(lfs_unmount(&lfs) == 0);

  CHECK(lfs_mount(&lfs, &cfg) == 0);
  check_all();
  CHECK(lfs_fs_gc(&lfs) == 0);
  CHECK(lfs_unmount(&lfs) == 0);

  printf("lfs_test: %d blocks in use; %s\n", (int)used, failures ? "FAIL" : "PASS");
  return failures != 0;
}
