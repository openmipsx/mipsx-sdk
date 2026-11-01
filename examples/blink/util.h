/* util.h: small helpers so the device build needs no C library.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef BLINK_UTIL_H
#define BLINK_UTIL_H

#include <stdint.h>

void *memcpy(void *dst, const void *src, unsigned n);
void *memset(void *dst, int c, unsigned n);
int memcmp(const void *a, const void *b, unsigned n);

/* Big-endian word at a byte position (the specs' byte order). */
static inline uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

static inline void put_be32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)v;
}

#endif
