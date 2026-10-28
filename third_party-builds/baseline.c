/* The run-time every test program links (crt0, picolibc's printf, the
 * helpers): subtracted from the programs' sizes.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdio.h>

int main(void)
{
  printf("%s %d\n", "baseline", 1);
  return 0;
}
