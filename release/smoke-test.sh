#!/bin/sh
# Check a MIPS-X toolchain release archive from a clean directory.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
#   release/smoke-test.sh mipsx-toolchain-<version>-<platform>.tar.xz
#
# Extracts the archive into a new temporary directory and, using only
# what it contains (no --sysroot, nothing from this checkout):
#   - compiles examples/hello.c (picolibc printf) at -O2 and -O0 and runs
#     it on the simulator with bin/mipsx-run;
#   - links a program with -mboard=device, packs it with bin/mipsx-pack and
#     checks the image with bin/mipsx-verify;
#   - runs the binary tools on the result;
#   - if cmake and ninja are installed, builds and runs a CMake project
#     with share/mipsx-sdk/cmake/mipsx-toolchain.cmake (ctest on the
#     simulator).
# Needs python3 (for the packer).

set -eu

archive=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
tmp=$(mktemp -d "${TMPDIR:-/tmp}/mipsx-smoke.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

cd "$tmp"
tar -xJf "$archive"
tc=$tmp/$(basename "$archive" .tar.xz)
bin=$tc/bin
test -x "$bin/clang" || { echo "no bin/clang in $archive" >&2; exit 1; }
cat "$tc/BUILDINFO"

say() { printf '== %s\n' "$*"; }

for opt in -O2 -O0; do
  say "hello.c $opt"
  "$bin/clang" --target=mipsx $opt "$tc/share/mipsx-sdk/examples/hello.c" -o hello
  out=$("$bin/mipsx-run" --expect-exit=0 hello)
  echo "$out"
  test "$out" = "Hello, world! 42"
done

say "device image"
cat > blink.c <<'EOF'
volatile int counter;
int main(void) {
  for (int i = 0; i < 10; i++)
    counter += i;
  return counter == 45 ? 0 : 1;
}
EOF
"$bin/clang" --target=mipsx -Os -mboard=device blink.c -o blink
"$bin/mipsx-pack" blink -o blink.bin
"$bin/mipsx-verify" blink.bin

say "binary tools"
"$bin/llvm-readelf" -h blink | grep -q 'Stanford MIPS-X'
"$bin/llvm-objdump" -d blink | grep -q '<main>:'
"$bin/llvm-size" blink
"$bin/llvm-nm" blink | grep -q ' T main'
echo 'nop' | "$bin/llvm-mc" -triple=mipsx -filetype=obj -o nop.o
"$bin/llvm-ar" rcs libnop.a nop.o
"$bin/ld.lld" --version

if command -v cmake >/dev/null 2>&1 && command -v ninja >/dev/null 2>&1; then
  say "CMake project"
  mkdir proj
  cp "$tc/share/mipsx-sdk/examples/hello.c" proj/
  cat > proj/CMakeLists.txt <<'EOF'
cmake_minimum_required(VERSION 3.20)
project(hello C)
enable_testing()
add_executable(hello hello.c)
add_test(NAME hello COMMAND hello)
set_tests_properties(hello PROPERTIES PASS_REGULAR_EXPRESSION "Hello, world! 42")
EOF
  cmake -G Ninja -S proj -B proj/build \
    -DCMAKE_TOOLCHAIN_FILE="$tc/share/mipsx-sdk/cmake/mipsx-toolchain.cmake" >/dev/null
  cmake --build proj/build
  (cd proj/build && ctest --output-on-failure)
else
  say "CMake project: skipped (no cmake or ninja)"
fi

say "all passed"
