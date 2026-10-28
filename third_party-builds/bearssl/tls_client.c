/* A BearSSL TLS client, for measuring what a TLS client links: with
 * FULL_PROFILE, br_ssl_client_init_full() (every cipher suite and
 * algorithm); otherwise a minimal TLS 1.2 profile for HTTPS
 * provisioning: ECDHE_RSA and ECDHE_ECDSA with AES-128-GCM or
 * ChaCha20-Poly1305, SHA-256/384, P-256 and the "i15" and "m15" code,
 * which suits a CPU without a multiplier. On the simulator it builds a
 * ClientHello and checks the record header.
 *
 * Copyright 2026 The mipsx-sdk authors.
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdio.h>
#include <string.h>

#include "bearssl.h"

/* A placeholder trust anchor (a 2048-bit RSA modulus of 0xC5 bytes). */
static unsigned char ta_dn[] = { 0x30, 0x00 };
static unsigned char ta_n[256];
static unsigned char ta_e[] = { 0x01, 0x00, 0x01 };
static br_x509_trust_anchor tas[1];

static br_ssl_client_context cc;
static br_x509_minimal_context xc;
static unsigned char iobuf[BR_SSL_BUFSIZE_BIDI];

#ifndef FULL_PROFILE
static void client_profile(br_ssl_client_context *c, br_x509_minimal_context *x,
                           const br_x509_trust_anchor *ta, size_t ta_num)
{
  static const uint16_t suites[] = {
    BR_TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,
    BR_TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,
    BR_TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256,
    BR_TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256,
  };
  br_ssl_client_zero(c);
  br_ssl_engine_set_versions(&c->eng, BR_TLS12, BR_TLS12);
  br_ssl_engine_set_prf_sha256(&c->eng, &br_tls12_sha256_prf);
  br_ssl_engine_set_hash(&c->eng, br_sha256_ID, &br_sha256_vtable);
  br_ssl_engine_set_hash(&c->eng, br_sha384_ID, &br_sha384_vtable);
  br_ssl_engine_set_suites(&c->eng, suites, sizeof suites / sizeof suites[0]);
  br_ssl_engine_set_rsavrfy(&c->eng, &br_rsa_i15_pkcs1_vrfy);
  br_ssl_engine_set_ec(&c->eng, &br_ec_p256_m15);
  br_ssl_engine_set_ecdsa(&c->eng, &br_ecdsa_i15_vrfy_asn1);
  br_ssl_engine_set_gcm(&c->eng, &br_sslrec_in_gcm_vtable, &br_sslrec_out_gcm_vtable);
  br_ssl_engine_set_aes_ctr(&c->eng, &br_aes_ct_ctr_vtable);
  br_ssl_engine_set_ghash(&c->eng, &br_ghash_ctmul32);
  br_ssl_engine_set_chapol(&c->eng, &br_sslrec_in_chapol_vtable, &br_sslrec_out_chapol_vtable);
  br_ssl_engine_set_chacha20(&c->eng, &br_chacha20_ct_run);
  br_ssl_engine_set_poly1305(&c->eng, &br_poly1305_i15_run);

  br_x509_minimal_init(x, &br_sha256_vtable, ta, ta_num);
  br_x509_minimal_set_hash(x, br_sha256_ID, &br_sha256_vtable);
  br_x509_minimal_set_hash(x, br_sha384_ID, &br_sha384_vtable);
  br_x509_minimal_set_rsa(x, &br_rsa_i15_pkcs1_vrfy);
  br_x509_minimal_set_ecdsa(x, &br_ec_p256_m15, &br_ecdsa_i15_vrfy_asn1);
  br_ssl_engine_set_x509(&c->eng, &x->vtable);
}
#endif

int main(void)
{
  memset(ta_n, 0xC5, sizeof ta_n);
  tas[0].dn.data = ta_dn;
  tas[0].dn.len = sizeof ta_dn;
  tas[0].flags = BR_X509_TA_CA;
  tas[0].pkey.key_type = BR_KEYTYPE_RSA;
  tas[0].pkey.key.rsa.n = ta_n;
  tas[0].pkey.key.rsa.nlen = sizeof ta_n;
  tas[0].pkey.key.rsa.e = ta_e;
  tas[0].pkey.key.rsa.elen = sizeof ta_e;

#ifdef FULL_PROFILE
  br_ssl_client_init_full(&cc, &xc, tas, 1);
#else
  client_profile(&cc, &xc, tas, 1);
#endif
  br_ssl_engine_set_buffer(&cc.eng, iobuf, sizeof iobuf, 1);
  static const unsigned char seed[32] = "not random: simulator test only";
  br_ssl_engine_inject_entropy(&cc.eng, seed, sizeof seed);
  if (!br_ssl_client_reset(&cc, "provisioning.example.com", 0)) {
    printf("tls_client: reset failed, error %d\n", br_ssl_engine_last_error(&cc.eng));
    return 1;
  }

  size_t len;
  unsigned char *rec = br_ssl_engine_sendrec_buf(&cc.eng, &len);
  int ok = (br_ssl_engine_current_state(&cc.eng) & BR_SSL_SENDREC) && rec &&
           len > 50 && rec[0] == 22 && rec[1] == 3 && rec[5] == 1 &&
           (size_t)((rec[3] << 8) | rec[4]) + 5 == len;
  printf("tls_client: ClientHello record of %u bytes: %s\n", (unsigned)len,
         ok ? "PASS" : "FAIL");
  return !ok;
}
