# tests: C execution test suites on the simulator

Work package S14 of the LLVM backend plan. `run_tests.py` compiles C
test programs with `clang --target=mipsx` against the SDK sysroot, runs
them on `mipsx-sim` and sorts the results. Two suites:

| Suite | Source | Default `--src` |
|---|---|---|
| `builtins` | compiler-rt's builtins unit tests | `<llvm-bin>/../../compiler-rt/test/builtins/Unit` |
| `torture` | GCC C torture execute tests, from the LLVM test-suite | `../llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute` |

The LLVM test-suite is not part of the SDK; clone it next to it:

```
git clone --filter=blob:none --depth 1 https://github.com/llvm/llvm-test-suite ../llvm-test-suite
```

## Running

```
make sysroot MIPSX_LLVM_BIN=~/src/openmipsx/llvm-project/build/bin
python3 tests/run_tests.py torture --llvm-bin ~/src/openmipsx/llvm-project/build/bin
python3 tests/run_tests.py builtins --llvm-bin ~/src/openmipsx/llvm-project/build/bin -O 2 -v
```

| Option | Meaning |
|---|---|
| `-O N` | Optimisation level, repeatable (default `-O 0 -O 2`) |
| `-j N` | Parallel jobs (default: all CPUs) |
| `--filter REGEX` | Only test files whose name matches |
| `--libc auto\|sysroot\|mini` | The sysroot's `libc.a` (picolibc, S15) or the small test library in `support/` (default: `libc.a` if the sysroot has one) |
| `--cflags "..."` | Extra compiler flags, e.g. `"-mllvm -verify-machineinstrs"` |
| `--results FILE` | One tab-separated line per test and level: file, level, status, detail |
| `-v` | Print every test that did not pass or was unsupported |
| `--keep` | Keep the executables (in a temporary directory) |

The summary line per level gives the pass rate over the tests that ran:

```
torture -O2: 1514 tests, 100 unsupported, 1414 run: 1414 pass (100.0%)
```

## Statuses

| Status | Meaning |
|---|---|
| `PASS` | Exit status 0 |
| `FAIL` | Non-zero exit status (`abort()` gives 134) |
| `HAZARD` | The simulator stopped: pipeline hazard, misaligned access or other error (status 125) |
| `TIMEOUT` | Cycle limit (`--max-cycles`, default 10⁹, as the simulator) or wall clock (`--run-timeout`, 120 s) |
| `CRASH` | The compiler crashed or reported an internal error |
| `CERROR` | The compiler rejected the test |
| `LERROR` | Link error on a `__*` runtime symbol, or another link error |
| `UNSUPPORTED` | Not run: see below |

Unsupported tests:

- **torture**: the test-suite's own skip lists in its `CMakeLists.txt`
  (GCC extensions Clang lacks, undefined behaviour, the MIPS list:
  `__builtin_setjmp`, `__int128`); the tests that need a file system
  (`fprintf-2.c`, `printf-2.c`, `user-printf.c`) or `mmap`; and
  per-test flags (`-fwrapv`, `-Wno-return-type`, `dg-options`) are applied
  as the test-suite does.
- **builtins**: tests whose `REQUIRES` names something not built for
  MIPS-X (`int128`, `x86-target-arch`, the `tf`/`xf`/`vfp` functions),
  tests of functions not in `libbuiltins.a`, non-standard `RUN` lines,
  and tests that print "skipped" (128-bit ones).
- either: a missing header or libc function (with `--libc mini`).

## The test library (`support/`)

Before picolibc (S15) the tests linked against `support/minilibc.c` and
the headers in `support/include`: output through the simulator's I/O
page, a bump allocator from `_end`, `printf` with integer, string and
simple floating-point conversions, the string functions, `qsort`,
`abort` (exit 134) and `exit`. It is not a C library; `--libc mini`
still selects it, which keeps the compiler tests independent of picolibc.

## Results

The pass rates per session are in the S14 row of the backend plan
(§5).
