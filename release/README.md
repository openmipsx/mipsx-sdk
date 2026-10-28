# release: toolchain archives and container image

| File | What |
|---|---|
| `package.py` | Assembles `mipsx-toolchain-<version>-<platform>.tar.xz` from an LLVM build of the fork, this SDK and picolibc |
| `smoke-test.sh` | Checks an archive from a clean directory, using nothing else |
| `TOOLCHAIN.md` | The archive's `README.md`: contents and use |
| `mipsx-toolchain.cmake` | CMake toolchain file for the archive layout (wraps `cmake/mipsx.cmake`) |
| `examples/hello.c` | Installed as `share/mipsx-sdk/examples/hello.c` |
| `Containerfile` | Debian image with an archive unpacked in `/opt/mipsx` |
| `refs` | The LLVM fork and picolibc commits that `release.yml` builds |

## Making an archive locally

```
python3 release/package.py --llvm-build ~/src/openmipsx/llvm-project/build --version 0.1
release/smoke-test.sh build/dist/mipsx-toolchain-0.1-linux-x86_64.tar.xz
```

`package.py` installs `clang`, `lld`, Clang's headers and the LLVM binary
tools from the build directory with `cmake --install --component ...
--strip` (the build must have them: `ninja $(release/package.py
--print-targets)`), copies this SDK (without `build/`) and picolibc
(`--picolibc`, default `../picolibc`; `none` for no C library) into the
work directory (`build/release`), builds the simulator, the run-time
sysroot and picolibc there with the installed Clang into
`lib/clang-runtimes/mipsx`, adds the simulator, the packer, the CMake and
Meson files and the docs, records the commits in `BUILDINFO`, and writes
the archive and its `.sha256` to `build/dist`. compiler-rt's builtins
come from the build's own source tree (`--llvm-src`).

`smoke-test.sh` unpacks the archive into a temporary directory and, with
only its contents, compiles `hello.c` (picolibc `printf`) at `-O2` and
`-O0` and runs it on the simulator, links, packs and verifies a
`-mboard=device` program, runs the binary tools, and builds and runs a
CMake project with `ctest` (if cmake and ninja are installed).

## Container image

The build context needs `dist/` with the Linux archives:

```
docker build -f release/Containerfile -t mipsx-toolchain build
docker run --rm -v "$PWD:/work" mipsx-toolchain clang --target=mipsx -O2 hello.c -o hello
```

## CI

`.github/workflows/ci.yml` runs `make check` on Linux x86-64, Linux arm64
and macOS, and, once a release exists, downloads the latest Linux x86-64
archive, smoke-tests it and uses it to run `make check-llvm`, build the
sysroot and picolibc from the commit under test (compiler-rt and picolibc
checked out at the commits in its `BUILDINFO`) and run compiler-rt's
builtins tests on the simulator.

`.github/workflows/release.yml` builds LLVM at `refs` (or the commits
given to a manual run) on Linux x86-64 and arm64 (Ubuntu 22.04, for an
older glibc; libstdc++ linked statically) and macOS arm64 (macOS 12 and
later), packages and smoke-tests each archive and uploads it as a
workflow artifact. A `v*` tag also publishes the archives and
`SHA256SUMS` as a GitHub release and pushes
`ghcr.io/<owner>/mipsx-toolchain:<tag>` and `:latest` for linux/amd64 and
linux/arm64.

To release: update `refs` to the LLVM and picolibc commits to ship, run
the workflow by hand once to see it build, then tag:

```
git tag -a v0.1 -m "MIPS-X toolchain 0.1"
git push origin v0.1
```

The LLVM fork's own CI (build and lit tests) is
`.github/workflows/mipsx.yml` on its `mipsx` branch.
