# MIPS-X toolchain

Clang, lld and the LLVM binary tools with the experimental MIPSX target,
for the ES3890, the MIPS-X derived CPU in the Linksys (Sipura) SPA3000,
together with the mipsx-sdk run-time, simulator and image packer. The
file `BUILDINFO` names the commits it was built from.

```
export PATH=$PWD/bin:$PATH
clang --target=mipsx -O2 share/mipsx-sdk/examples/hello.c -o hello
mipsx-run hello
```

Clang finds the sysroot in `lib/clang-runtimes/mipsx` by itself: it links
`crt0.o`, the simulator's linker script `sim.ld`, `libbuiltins.a`,
`libsim.a` and picolibc's `libc.a`. `-mboard=device` links with
`device.ld` and `libdevice.a` for the SPA3000 instead (no stdio there
yet); `mipsx-pack prog -o prog.bin` turns such a program into an upgrade
image and `mipsx-verify prog.bin` checks one. Read
`share/mipsx-sdk/tools/README.md` before flashing anything.

## Contents

| Path | What |
|---|---|
| `bin/clang`, `clang++`, `clang-cpp` | C compiler (`--target=mipsx`) |
| `bin/ld.lld` | Linker |
| `bin/llvm-mc`, `llvm-objdump`, `llvm-readelf`, `llvm-readobj`, `llvm-nm`, `llvm-size`, `llvm-ar`, `llvm-ranlib`, `llvm-objcopy`, `llvm-strip`, `llvm-dwarfdump`, `llvm-symbolizer`, `llvm-addr2line`, `llvm-cxxfilt` | Assembler and binary tools |
| `bin/mipsx-sim`, `bin/mipsx-run` | Instruction-set simulator, and its wrapper for test harnesses (`--expect-exit=N`, `--print-exit`) |
| `bin/mipsx-pack`, `bin/mipsx-verify` | Image packer and verifier (need `python3`) |
| `lib/clang/<version>/include` | Clang's own headers |
| `lib/clang-runtimes/mipsx` | Sysroot: `crt0.o`, `sim.ld`, `device.ld`, `libbuiltins.a` (helpers, soft-float, atomics), `libsim.a`, `libdevice.a`, picolibc's headers, `libc.a` and `libm.a` |
| `share/mipsx-sdk/docs` | The ABI (`abi.md`) and the C library notes |
| `share/mipsx-sdk/cmake` | CMake toolchain files (below) |
| `share/mipsx-sdk/meson` | Meson cross file (below) |
| `share/mipsx-sdk/examples` | `hello.c` |
| `LICENSES/` | Licences of LLVM, mipsx-sdk and picolibc |

## CMake

```
cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=<toolchain>/share/mipsx-sdk/cmake/mipsx-toolchain.cmake -S . -B build
```

Programs run on the simulator through `CMAKE_CROSSCOMPILING_EMULATOR`, so
`ctest` works. `-DMIPSX_BOARD=device` builds for the SPA3000.

## Meson

Write a cross file with the toolchain's paths and give it before
`share/mipsx-sdk/meson/mipsx.txt`:

```
[constants]
llvm_bin = '<toolchain>/bin'
sdk = '<toolchain>/share/mipsx-sdk'
sysroot = '<toolchain>/lib/clang-runtimes/mipsx'
```

```
meson setup --cross-file paths.txt --cross-file <toolchain>/share/mipsx-sdk/meson/mipsx.txt build
```

## Licences

LLVM, Clang, lld and compiler-rt: Apache 2.0 with LLVM exceptions.
mipsx-sdk: Apache 2.0. picolibc: BSD-style licences, listed in
`LICENSES/picolibc.txt`.
