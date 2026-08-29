/* SPDX-License-Identifier: Apache-2.0 */
/**
 * Milestone DR23: OpenSSL 3.x Native Provider Plugin (`phoenix-pqc-provider`).
 * AMD Phoenix AIE2 / XDNA1 Hardware Acceleration Provider.
 *
 * Standards & Resource Citations:
 * 1. OpenSSL 3.0+ Provider API Specification
 * 2. NIST FIPS 203 (ML-KEM) & NIST FIPS 204 (ML-DSA)
 * 3. ETSI GS QKD 014 v1.1.1 (Hybrid QKD KEM)
 * 4. DOI: 10.5281/zenodo.22162273
 */

#ifndef PHOENIX_PQC_PROVIDER_H
#define PHOENIX_PQC_PROVIDER_H

#include <stdint.h>
#include <stddef.h>

#define PHOENIX_PROVIDER_NAME    "phoenix_pqc_provider"
#define PHOENIX_PROVIDER_VERSION "1.2.0"
#define PHOENIX_PROVIDER_DESC    "AMD Phoenix AIE2 / XDNA1 Hardware Accelerated PQC Provider"

#ifdef _WIN32
#  define PHOENIX_EXPORT __declspec(dllexport)
#else
#  define PHOENIX_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

PHOENIX_EXPORT int OSSL_provider_init(
    const void *handle,
    const void *in,
    const void **out,
    void **provctx
);

#ifdef __cplusplus
}
#endif

#endif /* PHOENIX_PQC_PROVIDER_H */
