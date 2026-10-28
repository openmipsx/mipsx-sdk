/* main() for BearSSL's test_crypto.c on the simulator, which has no
 * argv: the test names come from stdin, one or more per line, and an
 * empty stdin means "all".  test_crypto.c is built with
 * -Dmain=bearssl_test_main.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdio.h>
#include <string.h>

int bearssl_test_main(int argc, char *argv[]);

int main(void)
{
  static char line[1024];
  static char *argv[64] = { "testcrypto" };
  int argc = 1;
  size_t n = 0;
  int c;
  while (n + 1 < sizeof line && (c = getchar()) != EOF)
    line[n++] = (char)c;
  line[n] = 0;
  for (char *t = strtok(line, " \t\r\n"); t && argc < 63; t = strtok(NULL, " \t\r\n"))
    argv[argc++] = t;
  if (argc == 1)
    argv[argc++] = "all";
  argv[argc] = NULL;
  return bearssl_test_main(argc, argv);
}
