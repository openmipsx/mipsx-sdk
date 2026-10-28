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
make MIPSX_LLVM_BIN=$PWD/../../llvm-project/build/bin               # -Os, with assertions
make MIPSX_LLVM_BIN=... OPT=-O2 ASSERT=0                            # -O2, release
make check MIPSX_LLVM_BIN=...                                       # self-tests
make check-pk-kat MIPSX_LLVM_BIN=...                                # RSA/EC known answers, cycles (2 min)
make check-bearssl MIPSX_LLVM_BIN=...                               # that, then BearSSL's test vectors (slow)
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
| `bearssl/pk_kat.c` | Known answers for the public-key code of a TLS client, with BearSSL's own vectors (it includes `test/test_crypto.c`): RSA-1024/2048 public operation and PKCS#1 verification (`i15`, `i31`), P-256 `mul`/`mulgen` and ECDSA verification (`p256_m15`, `prime_i15`), a P-384 ECDSA verification, X25519 (`c25519_m15`); one line per operation with its simulator cycles. Also built for the host (`build/host/`, nanoseconds) as a reference |
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
also pass `-mllvm -verify-machineinstrs`.

BearSSL `test_crypto` (`make check-bearssl`, -Os and -O2 with
assertions, a limit of 2×10¹⁰ cycles per test): 34 pass, 9 n/a (code
for x86 or POWER only), none fail. The other 14 reach the cycle limit
without a failure: DES (Monte Carlo), HMAC (the constant-time
`br_hmac_outCT` over every length), RSA and the elliptic-curve tests
(big-number arithmetic with no multiplier, so mostly in `__mulsi3` and
`__muldi3`). The DES, HMAC, C25519 and ECDSA ones print some passed
vectors before the limit; the RSA and EC_prime ones do not get through
their first vector. The results are in `build/*/bearssl_tests.txt`.

Those 14 are slow, not wrong: `pk_kat` (`make check-pk-kat`, run first
by `check-bearssl`) checks the operations a TLS client needs and
passes at -Os and -O2, matching the host. Cycles per operation at -Os
(-O2 is within 2%), and the time at the guessed 81 MHz (hardware.md;
the simulator does not model cache misses, so these are lower bounds):

| Operation | Cycles | at 81 MHz | Before |
|---|---|---|---|
| RSA-1024 public, `i15` | 9.7 M | 0.12 s | 12.7 M |
| RSA-2048 public or PKCS#1 verify, `i15` / `i31` | 37.4 M / 40.3 M | 0.46 s / 0.50 s | 47.4 M / 40.4 M |
| P-256 `mul` / `mulgen`, `p256_m15` | 70.6 M / 46.8 M | 0.87 s / 0.58 s | 56.2 M / 37.8 M |
| P-256 ECDSA verify, `p256_m15` | 123 M | 1.52 s | 104 M |
| P-256 `mul`, `mulgen`, `prime_i15` | 89.2 M | 1.10 s | 119 M |
| P-256 ECDSA verify, `prime_i15` | 179 M | 2.21 s | 238 M |
| P-384 ECDSA verify, `prime_i15` | 519 M | 6.4 s | 701 M |
| X25519, `c25519_m15` | 36.2 M | 0.45 s | 28.4 M |

"Before" is llvm-project 6fd9ed531416 with the old `__mulsi3` (mipsx-sdk
012492c). Since then the compiler multiplies inline with `mstep` when
known bits show an operand fits in 17 bits or fewer (llvm-project
d63693be8e1f), which helps the `i15` code (it masks its words with
`0x7FFF`): RSA −21%, `prime_i15` −25%. And `__mulsi3` is now
constant-time, always 32 steps (35 cycles, where it took 14 to 48
depending on the operands), which costs the `m15` code 23–27%: their
limbs come from memory, so the compiler cannot see that they are narrow,
and every product still calls `__mulsi3`. Before, X25519 took 28.4 M
cycles for the RFC 7748 inputs but 27.8 M for 9 × 9: the timing
depended on the secret scalar. Now all three take 36.2 M.

The public-key work of one TLS 1.2 handshake, with a two-certificate
chain: ECDHE_RSA with RSA-2048 certificates and X25519, three RSA
verifications and two X25519 multiplications, is about 185 M cycles
(2.3 s; 6.8 s if the CPU runs at the crystal's 27 MHz); with P-256
instead of X25519, 230 M (2.8 s). ECDHE_ECDSA with P-256 certificates
is about 490 M (6 s), and a P-384 intermediate (common in ECDSA
chains) adds 520 M (6.4 s), too slow. So the
provisioning server should use RSA certificates (or ECDSA P-256 only),
and the client could add X25519: `tls_client_min` sets only
`br_ec_p256_m15`, which has neither X25519 nor P-384; `br_ec_all_m15`
has both.

Most of the `m15` time is `__mulsi3` (before the constant-time change,
64% of a `p256_m15` multiplication and 71% of X25519: about 1.4 M calls
for one P-256 `mul`). BearSSL's `MUL15(x, y)` promises 15-bit operands
but does not show it: an experiment with `((x) & 0x7FFF) * (y)` in
`inner.h` takes P-256 ECDSA verify to 75 M cycles (`mul` 40.8 M), inline
and constant-time, but breaks `c25519_m15`, which passes wider operands
to some `MUL15`s; a patch would have to check each use. BearSSL's
Karatsuba code for slow multipliers (`-DBR_SLOW_MUL15=1`) was 8% faster
for P-256 and 4% for X25519 with the old `__mulsi3`, and passes
`pk_kat`. `-DBR_CT_MUL15=1` does nothing here: Clang removes the
`| 0x80000000` that it relies on, since only the low 31 bits of the
product are used. `__muldi3` (BearSSL's `i31`/`m31` code, `ghash_ctmul`)
is still not constant-time: it skips terms when a high word or the top
half of the low word of b is 0.

## Sizes

Bytes linked into the test programs from each library (`sizes.py`):
flash = `.text` + `.rodata` (including the library's share of merged
strings, an upper bound) + `.data`/`.sdata`. The run-time libraries
(picolibc's printf, the helpers) are extra, about 19 KB, and shared by
all components.

| Component | -Os | -Os, no asserts | -Oz, no asserts | -O2, no asserts |
|---|---|---|---|---|
| lwIP (all of the above) | 103,295 | 82,381 | 80,361 | 99,365 |
| littlefs | 50,566 | 44,192 | 42,524 | 50,308 |
| BearSSL, minimal TLS 1.2 client | 89,411 | 89,411 | 85,739 | 107,559 |
| BearSSL, `br_ssl_client_init_full` | 124,831 | 124,831 | 121,079 | 152,807 |

The inline multiplications (llvm-project d63693be8e1f) add 1,184 bytes
to the minimal client at -Os (1.3%), 1,232 at -O2, and 36–48 to lwIP;
littlefs and `init_full` (its EC code is `m31`, 64-bit products) do not
change. At -Oz the compiler keeps the calls, so nothing changes. The
constant-time `__mulsi3` is 224 bytes smaller (in the run-time libraries).

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
