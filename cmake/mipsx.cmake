# CMake toolchain file for MIPS-X (the ES3890) with Clang and the mipsx-sdk.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
#   cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=/path/to/mipsx-sdk/cmake/mipsx.cmake \
#         -DMIPSX_LLVM_BIN=/path/to/llvm-project/build/bin -S . -B build
#
# MIPSX_LLVM_BIN (or the environment variable of that name) is the
# directory holding clang, ld.lld and llvm-ar.  MIPSX_SYSROOT defaults to
# the SDK's build/sysroot (make sysroot, make libc).  MIPSX_BOARD is sim
# (the default) or device; it picks the linker script and board library
# that Clang's driver links, with crt0.o, libbuiltins.a and libc.a.
# Executables run on the simulator through CMAKE_CROSSCOMPILING_EMULATOR,
# so add_test() and ctest work.

set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR mipsx)

get_filename_component(_mipsx_sdk "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

if(NOT MIPSX_LLVM_BIN AND DEFINED ENV{MIPSX_LLVM_BIN})
  set(MIPSX_LLVM_BIN "$ENV{MIPSX_LLVM_BIN}")
endif()
if(NOT MIPSX_LLVM_BIN)
  message(FATAL_ERROR "mipsx.cmake: set MIPSX_LLVM_BIN to the directory holding clang and ld.lld")
endif()
set(MIPSX_SYSROOT "${_mipsx_sdk}/build/sysroot" CACHE PATH "mipsx-sdk sysroot")
set(MIPSX_BOARD sim CACHE STRING "Board to link for: sim or device")

# try_compile projects see the same settings.
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES MIPSX_LLVM_BIN MIPSX_SYSROOT MIPSX_BOARD)

set(CMAKE_C_COMPILER "${MIPSX_LLVM_BIN}/clang")
set(CMAKE_CXX_COMPILER "${MIPSX_LLVM_BIN}/clang++")
set(CMAKE_ASM_COMPILER "${MIPSX_LLVM_BIN}/clang")
set(CMAKE_C_COMPILER_TARGET mipsx)
set(CMAKE_CXX_COMPILER_TARGET mipsx)
set(CMAKE_ASM_COMPILER_TARGET mipsx)
set(CMAKE_AR "${MIPSX_LLVM_BIN}/llvm-ar" CACHE FILEPATH "")
set(CMAKE_RANLIB "${MIPSX_LLVM_BIN}/llvm-ranlib" CACHE FILEPATH "")
set(CMAKE_NM "${MIPSX_LLVM_BIN}/llvm-nm" CACHE FILEPATH "")
set(CMAKE_OBJCOPY "${MIPSX_LLVM_BIN}/llvm-objcopy" CACHE FILEPATH "")
set(CMAKE_OBJDUMP "${MIPSX_LLVM_BIN}/llvm-objdump" CACHE FILEPATH "")
set(CMAKE_STRIP "${MIPSX_LLVM_BIN}/llvm-strip" CACHE FILEPATH "")
set(CMAKE_SIZE "${MIPSX_LLVM_BIN}/llvm-size" CACHE FILEPATH "")

set(CMAKE_SYSROOT "${MIPSX_SYSROOT}")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-mboard=${MIPSX_BOARD}")

# Only the simulator can run programs here.
if(MIPSX_BOARD STREQUAL "sim")
  set(CMAKE_CROSSCOMPILING_EMULATOR "${_mipsx_sdk}/sim/mipsx-run")
endif()

set(CMAKE_FIND_ROOT_PATH "${MIPSX_SYSROOT}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(CMAKE_EXECUTABLE_SUFFIX_C "")
