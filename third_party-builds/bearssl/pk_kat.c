/* Known-answer tests for the public-key code a BearSSL TLS client runs:
 * RSA public operation and PKCS#1 v1.5 verification (i15, i31), P-256
 * point multiplication (p256_m15, prime_i15: mul, mulgen, and muladd
 * through ECDSA verification, plus a P-384 ECDSA verification) and
 * X25519 (c25519_m15). One or two
 * vectors per primitive, all from BearSSL's test/test_crypto.c, which is
 * included here for its keys and helpers.
 *
 * Prints one line per operation: name, ok or FAIL, and its cost
 * (simulator cycles on MIPS-X, from the I/O page cycle counter;
 * nanoseconds on the host). Exits non-zero if any check failed.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
/* Its main() becomes an unused static function. */
static int bearssl_test_main(int argc, char *argv[]);
#define main bearssl_test_main
#include "test_crypto.c"
#undef main

#ifdef __mipsx__
#define UNIT "cycles"
static uint64_t now(void)
{
  uint32_t lo = *(volatile uint32_t *)0xFFFF0008; /* latches the high word */
  uint32_t hi = *(volatile uint32_t *)0xFFFF000C;
  return (uint64_t)hi << 32 | lo;
}
#else
#include <time.h>
#define UNIT "ns"
static uint64_t now(void)
{
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}
#endif

static int failures;
static uint64_t t0;

static void start(void)
{
  t0 = now();
}

static void report(const char *name, int ok)
{
  uint64_t t = now() - t0;
  printf("%-44s %-4s %12llu %s\n", name, ok ? "ok" : "FAIL",
         (unsigned long long)t, UNIT);
  fflush(stdout);
  if (!ok)
    failures++;
}

/* The PKCS#1 v1.5 signature padding of a DigestInfo for a k-byte modulus. */
static void pkcs1_pad(unsigned char *dst, size_t k, const char *digest_info)
{
  unsigned char di[64];
  size_t n = hextobin(di, digest_info);
  dst[0] = 0x00;
  dst[1] = 0x01;
  memset(dst + 2, 0xFF, k - 3 - n);
  dst[k - n - 1] = 0x00;
  memcpy(dst + k - n, di, n);
}

/* From test_RSA_core(): signatures computed with OpenSSL. */
static const char RSA1024_SIG[] = "45A3DC6A106BCD3BD0E48FB579643AA3FF801E5903E80AA9B43A695A8E7F454E93FA208B69995FF7A6D5617C2FEB8E546375A664977A48931842AAE796B5A0D64393DCA35F3490FC157F5BD83B9D58C2F7926E6AE648A2BD96CAB8FCCD3D35BB11424AD47D973FF6D69CA774841AEC45DFAE99CCF79893E7047FDE6CB00AA76D";
static const char RSA1024_DI[] = "3021300906052B0E03021A05000414A94A8FE5CCB19BA61C4C0873D391E987982FBBD3";
static const char RSA1024_BAD[] = "F27781B9B3B358583A24F9BA6B34EE98B67A5AE8D8D4FA567BA773EB6B85EF88848680640A1E2F5FD117876E5FB928B64C6EFC7E03632A3F4C941E15657C0C705F3BB8D0B03A0249143674DB1FE6E5406D690BF2DA76EA7FF3AC6FCE12C7801252FAD52D332BE4AB41F9F8CF1728CDF98AB8E8C20E0C350E4F707A6402C01E0B";
static const char RSA2048_SIG[] = "B188ED4EF173A30AED3889926E3CF1CE03FE3BAA7AB122B119A8CD529062F235A7B321008FB898894A624B3E6C8C5374950E78FAC86651345FE2ABA0791968284F23B0D794F8DCDDA924518854822CB7FF2AA9F205AACD909BB5EA541534CC00DBC2EF7727B9FE1BAFE6241B931E8BD01E13632E5AF9E94F4A335772B61F24D6F6AA642AEABB173E36F546CB02B19A1E5D4E27E3EB67F2E986E9F084D4BD266543800B1DC96088A05DFA9AFA595398E9A766D41DD8DA4F74F36C9D74867F0BF7BFA8622EE43C79DA0CEAC14B5D39DE074BDB89D84145BC19D8B2D0EA74DBF2DC29E907BF7C7506A2603CD8BC25EFE955D0125EDB2685EF158B020C9FC539242A";
static const char RSA2048_DI[] = "3031300D060960864801650304020105000420A5A0A792A09438811584A68E240C6C89F1FB1C53C0C86E270B942635F4F6B24A";
static const char RSA2048_HASH[] = "A5A0A792A09438811584A68E240C6C89F1FB1C53C0C86E270B942635F4F6B24A";

static void test_rsa(const char *impl, br_rsa_public pub, br_rsa_pkcs1_vrfy vrfy)
{
  unsigned char x[256], ref[256], sig[256], hash[32], out[32];
  char name[64];
  size_t len;
  int ok;

  len = hextobin(x, RSA1024_SIG);
  pkcs1_pad(ref, len, RSA1024_DI);
  snprintf(name, sizeof name, "rsa_%s_public 1024", impl);
  start();
  ok = pub(x, len, &RSA_PK) == 1;
  report(name, ok && memcmp(x, ref, len) == 0);

  len = hextobin(x, RSA1024_BAD);
  snprintf(name, sizeof name, "rsa_%s_public 1024 out of range", impl);
  start();
  report(name, pub(x, len, &RSA_PK) == 0);

  len = hextobin(x, RSA2048_SIG);
  pkcs1_pad(ref, len, RSA2048_DI);
  snprintf(name, sizeof name, "rsa_%s_public 2048", impl);
  start();
  ok = pub(x, len, &RSA2048_PK) == 1;
  report(name, ok && memcmp(x, ref, len) == 0);

  len = hextobin(sig, RSA2048_SIG);
  hextobin(hash, RSA2048_HASH);
  snprintf(name, sizeof name, "rsa_%s_pkcs1_vrfy 2048 sha256", impl);
  start();
  ok = vrfy(sig, len, BR_HASH_OID_SHA256, sizeof out, &RSA2048_PK, out) == 1;
  report(name, ok && memcmp(out, hash, sizeof out) == 0);

  sig[100] ^= 0x04;
  snprintf(name, sizeof name, "rsa_%s_pkcs1_vrfy 2048 bad sig", impl);
  start();
  ok = vrfy(sig, len, BR_HASH_OID_SHA256, sizeof out, &RSA2048_PK, out) == 0
       || memcmp(out, hash, sizeof out) != 0;
  report(name, ok);
}

/* From test_EC_KAT() and test_EC_P256_carry(). */
static const char P256_K[] = "C9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721";
static const char P256_KG[] = "0460FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB67903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299";
static const char P256_CARRY_P[] = "0435BAA24B2B6E1B3C88E22A383BD88CC4B9A3166E7BCF94FF6591663AE066B33B821EBA1B4FC8EA609A87EB9A9C9A1CCD5C9F42FA1365306F64D7CAA718B8C978";
static const char P256_CARRY_Q[] = "0447752A76CA890328D34E675C4971EC629132D1FC4863EDB61219B72C4E58DC5E9D51E7B293488CFD913C3CF20E438BB65C2BA66A7D09EABB45B55E804260C5EB";

static void test_ecdsa(const char *impl, const br_ec_impl *ec, size_t v)
{
  const ecdsa_kat_vector *kv = &ECDSA_KAT[v];
  unsigned char hash[64], sig[150];
  br_hash_compat_context hc;
  size_t hash_len, sig_len;
  char name[64];
  const char *hn = kv->hf == &br_sha256_vtable ? "sha256" : "sha1";
  const char *cn = kv->pub == &EC_P384_PUB ? "P-384 " : "";

  if (kv->pub != &EC_P256_PUB && kv->pub != &EC_P384_PUB) {
    printf("ECDSA_KAT[%u] is not a P-256 or P-384 vector\n", (unsigned)v);
    failures++;
    return;
  }
  kv->hf->init(&hc.vtable);
  kv->hf->update(&hc.vtable, kv->msg, strlen(kv->msg));
  kv->hf->out(&hc.vtable, hash);
  hash_len = (kv->hf->desc >> BR_HASHDESC_OUT_OFF) & BR_HASHDESC_OUT_MASK;

  sig_len = hextobin(sig, kv->sraw);
  snprintf(name, sizeof name, "ecdsa_i15_vrfy_raw %s %s%s", impl, cn, hn);
  start();
  report(name, br_ecdsa_i15_vrfy_raw(ec, hash, hash_len, kv->pub, sig, sig_len) == 1);

  sig_len = hextobin(sig, kv->sasn1);
  snprintf(name, sizeof name, "ecdsa_i15_vrfy_asn1 %s %s%s", impl, cn, hn);
  start();
  report(name, br_ecdsa_i15_vrfy_asn1(ec, hash, hash_len, kv->pub, sig, sig_len) == 1);

  hash[0] ^= 0x80;
  snprintf(name, sizeof name, "ecdsa_i15_vrfy_asn1 %s %sbad hash", impl, cn);
  start();
  report(name, br_ecdsa_i15_vrfy_asn1(ec, hash, hash_len, kv->pub, sig, sig_len) == 0);
}

static void test_p256(const char *impl, const br_ec_impl *ec)
{
  unsigned char k[32], ref[65], p[65], q[65], one[1] = { 0x10 };
  size_t glen;
  char name[64];
  int ok;

  hextobin(k, P256_K);
  hextobin(ref, P256_KG);
  memcpy(p, ec->generator(BR_EC_secp256r1, &glen), sizeof p);
  snprintf(name, sizeof name, "ec_%s mul P-256", impl);
  start();
  ok = glen == sizeof p && ec->mul(p, sizeof p, k, sizeof k, BR_EC_secp256r1) == 1;
  report(name, ok && memcmp(p, ref, sizeof p) == 0);

  memset(p, 0, sizeof p);
  snprintf(name, sizeof name, "ec_%s mulgen P-256", impl);
  start();
  ok = ec->mulgen(p, k, sizeof k, BR_EC_secp256r1) == sizeof p;
  report(name, ok && memcmp(p, ref, sizeof p) == 0);

  hextobin(p, P256_CARRY_P);
  hextobin(q, P256_CARRY_Q);
  snprintf(name, sizeof name, "ec_%s mul P-256 carry (k=16)", impl);
  start();
  ok = ec->mul(p, sizeof p, one, 1, BR_EC_secp256r1) == 1;
  report(name, ok && memcmp(p, q, sizeof p) == 0);

  test_ecdsa(impl, ec, 0); /* RFC 6979 A.2.5, SHA-1, "sample" */
  test_ecdsa(impl, ec, 2); /* RFC 6979 A.2.5, SHA-256, "sample" */
}

static void test_x25519(void)
{
  unsigned char u[32], k[32], ref[32];
  char name[64];
  size_t v;
  int ok;

  for (v = 0; C25519_KAT[v].scalar; v++) {
    hextobin(k, C25519_KAT[v].scalar);
    hextobin(u, C25519_KAT[v].u_in);
    hextobin(ref, C25519_KAT[v].u_out);
    snprintf(name, sizeof name, "ec_c25519_m15 mul (RFC 7748 #%u)", (unsigned)v + 1);
    start();
    ok = br_ec_c25519_m15.mul(u, sizeof u, k, sizeof k, BR_EC_curve25519) == 1;
    report(name, ok && memcmp(u, ref, sizeof u) == 0);
  }

  /* The first step of test_EC_c25519()'s iteration: 9 * 9. */
  memset(u, 0, sizeof u);
  u[0] = 9;
  memcpy(k, u, sizeof k);
  hextobin(ref, "422C8E7A6227D7BCA1350B3E2BB7279F7897B87BB6854B783C60E80311AE3079");
  start();
  ok = br_ec_c25519_m15.mul(u, sizeof u, k, sizeof k, BR_EC_curve25519) == 1;
  report("ec_c25519_m15 mul (9*9)", ok && memcmp(u, ref, sizeof u) == 0);
}

int main(void)
{
  test_rsa("i15", br_rsa_i15_public, br_rsa_i15_pkcs1_vrfy);
  test_rsa("i31", br_rsa_i31_public, br_rsa_i31_pkcs1_vrfy);
  test_p256("p256_m15", &br_ec_p256_m15);
  test_p256("prime_i15", &br_ec_prime_i15);
  /* P-384 goes to prime_i15 (as in br_ec_all_m15); ECDSA certificate
     chains often have a P-384 intermediate. RFC 6979 A.2.6, SHA-256. */
  test_ecdsa("prime_i15", &br_ec_prime_i15, 12);
  test_x25519();
  printf("%s: %d failure%s\n", failures ? "FAIL" : "PASS", failures,
         failures == 1 ? "" : "s");
  return failures != 0;
}
