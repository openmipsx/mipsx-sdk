# Third-party libraries for the firmware

Builds of three libraries from the open-source stack plan (lwIP, littlefs
and BearSSL) with Clang for MIPS-X, their self-tests on the simulator,
and a size report. The sources are upstream checkouts, unmodified:

| Library | Version | Upstream | Checkout |
|---|---|---|---|
| lwIP | 2.2.1 (`STABLE-2_2_1_RELEASE`, 77dcd25a7250) | https://github.com/lwip-tcpip/lwip | `../../third_party/lwip` |
| littlefs | 2.11.3 (`v2.11.3`, 6cb4e86540ec) | https://github.com/littlefs-project/littlefs | `../../third_party/littlefs` |
| BearSSL | 0.6 (`v0.6`, 8ef7680081c6) | https://www.bearssl.org/git/BearSSL | `../../third_party/bearssl` |

```
git clone --branch STABLE-2_2_1_RELEASE https://github.com/lwip-tcpip/lwip third_party/lwip
git clone --branch v2.11.3 https://github.com/littlefs-project/littlefs third_party/littlefs
git clone --branch v0.6 https://www.bearssl.org/git/BearSSL third_party/bearssl
```

## Building and testing

Needs the sysroot (`make sysroot libc` at the top of the SDK) and the
simulator.

```
make MIPSX_LLVM_BIN=~/src/mipsx/llvm-project/build/bin             # -Os, with assertions
make MIPSX_LLVM_BIN=... OPT=-O2 ASSERT=0                            # -O2, release
make check MIPSX_LLVM_BIN=...                                       # self-tests
make check-bearssl MIPSX_LLVM_BIN=...                               # BearSSL's test vectors (slow)
make sizes MIPSX_LLVM_BIN=...                                       # all four builds and the size table
```

Output goes to `build/<opt>[-noassert]/` (`TAG=x-` prefixes the
directory, for comparing compilers). Everything is compiled with
`-ffunction-sections -fdata-sections` and linked with `--gc-sections`;
`ASSERT=0` adds `-DNDEBUG -DLWIP_NOASSERT -DLFS_NO_ASSERT`.

| File | What |
|---|---|
| `lwip/lwipopts.h`, `lwip/arch/cc.h` | lwIP configuration: `NO_SYS`, IPv4 only, Ethernet + ARP, TCP, UDP, ICMP, DHCP, DNS, IP fragmentation, loopback; apps SNTP, TFTP and httpd (built-in pages, no CGI/SSI); 16 KB heap, 16 pool pbufs; big-endian |
| `lwip/lwip_test.c` | TCP echo (20000 bytes) and UDP (1 to 3000 bytes, so fragmented) over the loopback interface; then a dummy Ethernet interface with DHCP, httpd, TFTP and SNTP started, checking the IP header checksum of every frame sent |
| `littlefs/lfs_test.c` | littlefs on its RAM block device (32 blocks of 4 KB): format, directories, files of 0 to 20000 bytes, 400 rewrites of a config file (`block_cycles` 100, so compaction and relocation), seek, overwrite, truncate, rename, remove, unmount and remount with every check repeated, `lfs_fs_gc` |
| `bearssl/tls_client.c` | A TLS client that builds a ClientHello and checks its record header; `tls_client_full` uses `br_ssl_client_init_full`, `tls_client_min` a TLS 1.2 profile for HTTPS provisioning (ECDHE_RSA/ECDHE_ECDSA, AES-128-GCM or ChaCha20-Poly1305, SHA-256/384, P-256, the `i15`/`m15` code and `x509_minimal`) |
| `bearssl/test_main.c`, `run_bearssl_tests.sh` | BearSSL's `test/test_crypto.c` (all its known-answer tests), one simulator run per test, test names on stdin since the simulator has no argv |
| `baseline.c` | printf only |
| `sizes.py` | Bytes each library contributes to each linked program, from lld's map file |

littlefs's own test runner (`runners/test_runner.c` with the TOML test
cases) needs argv, files and a host-side Python driver, and lwIP's unit
tests need the `check` library and fork, so `lfs_test.c` and
`lwip_test.c` stand in for them.

## Results

Simulator, llvm-project `mipsx` at the S16 commits: `lwip_test`,
`lfs_test`, `tls_client_min` and `tls_client_full` pass at -Os and -O2,
with and without assertions, and at -Oz without; the -Os and -O2 builds
also pass `-mllvm -verify-machineinstrs`. BearSSL `test_crypto`: see
[S16 in the LLVM plan](../../linksys-spa3000/docs/plan/llvm-backend.md)
and `build/*/bearssl_tests.txt`.

## Sizes

Bytes linked into the test programs from each library (`sizes.py`):
flash = `.text` + `.rodata` (including the library's share of merged
strings, an upper bound) + `.data`/`.sdata`. The run-time libraries
(picolibc's printf, the helpers) are extra, about 19 KB, and shared by
all components.

| Component | -Os | -Os, no asserts | -Oz, no asserts | -O2, no asserts |
|---|---|---|---|---|
| lwIP (all of the above) | 103,247 | 82,345 | 80,361 | 99,329 |
| littlefs | 50,566 | 44,192 | 42,524 | 50,308 |
| BearSSL, minimal TLS 1.2 client | 88,227 | 88,227 | 85,739 | 106,327 |
| BearSSL, `br_ssl_client_init_full` | 124,831 | 124,831 | 121,079 | 152,807 |

RAM: lwIP's `.bss` is 46 KB with this `lwipopts.h` (heap and pools);
BearSSL's client needs `BR_SSL_BUFSIZE_BIDI` (about 33 KB) of I/O
buffer plus its contexts; littlefs needs its `lfs_t` and caches, a few
hundred bytes here.

For comparison, the same sources at -Os without assertions, unlinked
(sum of `llvm-size` text over all objects, so including code the
programs do not use), with Debian's Clang 19 for other 32-bit targets:

| Library | MIPS-X | MIPS32 | RV32I | RV32IMC | Thumb-2 (v7-M) |
|---|---|---|---|---|---|
| lwIP | 90,475 | 81,776 | 70,620 | 52,306 | 44,386 |
| littlefs | 46,438 | 37,546 | 32,406 | 21,950 | 20,680 |
| BearSSL (all of it) | 319,642 | 292,930 | 293,342 | 200,816 | 169,822 |

MIPS-X code is 9–24% larger than MIPS32: no load-upper-immediate (an
address is three instructions), no multiplier (calls to `__mulsi3`), two
delay slots on every branch, and a load delay with no interlock.
