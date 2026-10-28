# CMake toolchain file for a MIPS-X toolchain release archive.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Installed as share/mipsx-sdk/cmake/mipsx-toolchain.cmake:
#
#   cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=<toolchain>/share/mipsx-sdk/cmake/mipsx-toolchain.cmake \
#         -S . -B build
#
# Points the SDK's mipsx.cmake (next to this file) at the release's own
# bin/ and sysroot (lib/clang-runtimes/mipsx).  MIPSX_BOARD works as there.

get_filename_component(_mipsx_prefix "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
if(NOT MIPSX_LLVM_BIN)
  set(MIPSX_LLVM_BIN "${_mipsx_prefix}/bin")
endif()
set(MIPSX_SYSROOT "${_mipsx_prefix}/lib/clang-runtimes/mipsx" CACHE PATH "mipsx-sdk sysroot")
include("${CMAKE_CURRENT_LIST_DIR}/mipsx.cmake")
