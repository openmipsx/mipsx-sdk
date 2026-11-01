/* util.c: memcpy, memset and memcmp for the device build.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 *
 * The compiler may call these for aggregate copies even with
 * -fno-builtin, so the example defines them itself instead of relying
 * on the C library being linked.  Plain byte loops; speed does not
 * matter here.
 */
#include "util.h"

void *memcpy(void *dst, const void *src, unsigned n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    while (n--)
        *d++ = *s++;
    return dst;
}

void *memset(void *dst, int c, unsigned n)
{
    uint8_t *d = dst;
    while (n--)
        *d++ = (uint8_t)c;
    return dst;
}

int memcmp(const void *a, const void *b, unsigned n)
{
    const uint8_t *p = a, *q = b;
    while (n--) {
        if (*p != *q)
            return *p < *q ? -1 : 1;
        p++;
        q++;
    }
    return 0;
}
