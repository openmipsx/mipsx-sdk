// Hello world for the MIPS-X toolchain release.
// SPDX-License-Identifier: Apache-2.0
//
//   clang --target=mipsx -O2 hello.c -o hello
//   mipsx-run hello
//
// On the simulator, stdio goes through its I/O page (docs/abi.md §13.5).

#include <stdio.h>

int main(void) {
  printf("Hello, world! %d\n", 6 * 7);
  return 0;
}
