/* lwIP architecture header for MIPS-X (the ES3890) with picolibc.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef LWIP_ARCH_CC_H
#define LWIP_ARCH_CC_H

#include <stdio.h>
#include <stdlib.h>

/* MIPS-X is big-endian; lwIP assumes little-endian unless told. */
#define BYTE_ORDER BIG_ENDIAN

#define LWIP_ERRNO_INCLUDE <errno.h>
#define LWIP_TIMEVAL_PRIVATE 0

#define LWIP_PLATFORM_DIAG(x) do { printf x; } while (0)
#define LWIP_PLATFORM_ASSERT(x) \
  do { printf("lwIP assertion \"%s\" failed at %s:%d\n", x, __FILE__, __LINE__); \
       abort(); } while (0)

unsigned int mipsx_lwip_rand(void);
#define LWIP_RAND() (mipsx_lwip_rand())

#endif
