# picolibc for MIPS-X

Work package S15 of the LLVM backend plan. The C library is
[picolibc](https://github.com/picolibc/picolibc) 1.8.12 with a MIPS-X
port on branch `mipsx` of a local clone (by default `../picolibc`, next
to this SDK).

## Building

```
make libc MIPSX_LLVM_BIN=$PWD/../llvm-project/build/bin
```

builds the sysroot (`make sysroot`), configures picolibc with Meson in
`build/picolibc`, and installs it into `build/sysroot`: `include/`,
`lib/libc.a`, `lib/libm.a` (empty: picolibc puts libm in libc.a) and
`lib/libsemihost.a`. It then rebuilds `lib/libsim.a` with the objects of
`libsemihost.a` added, so programs for the simulator get stdio with no
extra flags:

```
clang --target=mipsx --sysroot=build/sysroot -O2 hello.c -o hello
sim/build/mipsx-sim hello
```

Meson comes from `pipx install meson` (1.12 was used). picolibc also
installs its own linker scripts (`picolibc*.ld`) and `libdummyhost.a`,
`libnosys.a` and `libg.a`; the Clang driver uses none of them.

Configuration (`libc.mk`, `PICOLIBC_OPTIONS`):

| Option | Why |
|---|---|
| `--buildtype=minsize` (`-Os`) | Code size matters on the device (picolibc's tests build at `-Oz`) |
| `-Dpicocrt=false` | The SDK's `crt0.o` starts programs (abi §13.3) |
| `-Dthread-local-storage=false` | No TLS (abi §1); `errno` is an ordinary global |
| `-Datomic-ungetc=false` | `ungetc` without atomics: one CPU, and stdio is not used from interrupt handlers |
| `-Dmultilib=false` | One ABI |

## What the port adds (picolibc branch `mipsx`)

- `libc/machine/mipsx/setjmp.S`: `setjmp`/`longjmp` saving the 13
  registers of abi §13.7; `_JBLEN` 13 in `machine/setjmp.h`.
- `machine/ieeefp.h`: `__IEEE_BIG_ENDIAN` for `__mipsx__` (Clang does not
  define `__FLOAT_WORD_ORDER__`).
- `libos/semihost/machine/mipsx`: `stdin`/`stdout` on the simulator's
  I/O page (abi §13.5), `stderr` on its stderr register, `read` (fd 0)
  and `write` (fds 1 and 2), and picolibc's fake versions of the file
  calls (open fails). `_exit` is not here: it comes from the board
  library `libsim.a`/`libdevice.a`.
- `meson.build`: a cross-file property `test_runtime_link_args` that
  links tests with the compiler driver's own start-up code, linker script
  and libraries instead of picolibc's `picocrt` and `picolibc.ld`.

The triple `mipsx` is not caught by picolibc's `mips` handling: Meson's
`cpu_family` is matched exactly (`libc/machine/<cpu_family>`, and the
alias table only maps `mips64`), and the headers test `__mips__`, which
Clang does not define for MIPS-X. The CMake build looks for
`libc/machine/${CMAKE_SYSTEM_PROCESSOR}`, also exactly; the port has a
`CMakeLists.txt` there, but only the Meson build was used.

SDK side: `rt/sim.ld` and `rt/device.ld` gained `.fini_array` (with
picolibc's `.fini_array_onexit`, which runs `atexit` handlers) and
`__heap_start`/`__heap_end` for `sbrk` (abi §13.1).

Board support: on the device there is no stdio yet (`printf` fails to
link: `stdout` is undefined) until a UART driver exists; everything else
in libc works.

## Cross files for other projects

`meson/mipsx.txt` is a Meson cross file for any project. It needs the
paths of the LLVM build, the SDK and the sysroot as constants from a
file given before it; `make meson-paths MIPSX_LLVM_BIN=...` writes that
file as `build/meson-paths.txt`:

```
meson setup --cross-file build/meson-paths.txt --cross-file meson/mipsx.txt build-x
meson test -C build-x          # runs on the simulator via sim/mipsx-run
```

`cmake/mipsx.cmake` is a CMake toolchain file:

```
cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=.../mipsx-sdk/cmake/mipsx.cmake \
      -DMIPSX_LLVM_BIN=.../llvm-project/build/bin -S . -B build-x
```

`MIPSX_SYSROOT` (default `build/sysroot`) and `MIPSX_BOARD` (`sim` or
`device`) can be set too; with `sim`, `ctest` runs tests on the
simulator (`CMAKE_CROSSCOMPILING_EMULATOR`).

## Testing

```
make check-libc MIPSX_LLVM_BIN=...
```

configures a second build, `build/picolibc-tests`, with `-Dtests=true
-Dtests-enable-posix-io=false` (the simulator has no files), builds what
the compiler can (`ninja -k 0`), and runs the built tests with
`meson/run-built-tests.py`: `meson test` with `sim/mipsx-run` as the exe
wrapper, no cycle limit and 20 times picolibc's timeouts.

Results on 2026-10-28, llvm-project `mipsx` at 3f189e4f0725 (S14's
compiler-rt builtins and atomics in `libbuiltins.a`): all 277 tests
build; 257 pass, 2 fail as expected (`test-hosted-exit-fail`,
`test-abort-failure`), 17 are skipped and 1 fails:

| Test | Result | Cause |
|---|---|---|
| `test-argv` | `mipsx-run` exits 126 on `--args hello world` | Not supported: no command-line arguments; crt0 calls `main(0, 0)` |

The skipped tests need files, directories or `rlimit`s, or are for other
targets (`test-riscv-jvt`, `test-scmpu`, …).

An earlier run with llvm-project at 67d0924e3e53 hit
[reload-earlyclobber](compiler-bugs/reload-earlyclobber.md): Clang
crashed on `strptime_l.c` at `-O2`/`-O3` and on two test programs, and
`test-fmemopen`, `tstring`, `strcmp-1`, `test-tgamma` and `test-jn`
failed at run time. S14's fix (8530b3a411c7) cleared all of them.

Long tests take minutes on the simulator (`test-memmem` about 4 minutes
on a loaded machine); the whole run takes about 15 minutes with 12
jobs.
