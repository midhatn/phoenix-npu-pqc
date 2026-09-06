// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR34: Hardware Root of Trust, TCG DICE / TPM Attestation & Enclave Security Boundaries.
 * Internal Header for AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#ifndef DR34_DICE_TPM_INTERNAL_HPP
#define DR34_DICE_TPM_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

namespace dr34 {

// Magic Header: "DICE" in ASCII (0x44494345)
constexpr uint32_t MAGIC_HEADER                  = 0x44494345;

// Operation Modes
constexpr uint32_t MODE_DICE_DERIVE_CDI          = 0x01; // Derive Compound Device Identifier
constexpr uint32_t MODE_DICE_EXTEND_PCR          = 0x02; // Extend measurement into PCR bank
constexpr uint32_t MODE_DICE_GENERATE_QUOTE      = 0x03; // Generate TPM 2.0 / DICE Attestation Quote
constexpr uint32_t MODE_DICE_VERIFY_QUOTE        = 0x04; // Verify Attestation Quote against PCR state
constexpr uint32_t MODE_DICE_ENCLAVE_SEAL        = 0x05; // Seal secret to PCR measurement policy

// PCR Index Constants (8 hardware registers on tile)
constexpr uint32_t PCR_0_FIRMWARE_BASE           = 0;
constexpr uint32_t PCR_1_TILE_DESCRIPTOR         = 1;
constexpr uint32_t PCR_2_SECURITY_CONFIG         = 2;
constexpr uint32_t PCR_3_RUNTIME_CALLER          = 3;
constexpr uint32_t PCR_4_EXT_ORACLE_HASH         = 4;
constexpr uint32_t PCR_5_ENTROPY_STATE           = 5;
constexpr uint32_t PCR_6_KEY_LIFECYCLE           = 6;
constexpr uint32_t PCR_7_ATTESTATION_NONCE       = 7;
constexpr uint32_t PCR_COUNT                     = 8;

// Status Codes
constexpr uint32_t STATUS_SUCCESS                = 0x00000000;
constexpr uint32_t STATUS_ERR_INVALID_MAGIC      = 0xDEAD3401;
constexpr uint32_t STATUS_ERR_PCR_OUT_OF_BOUNDS  = 0xDEAD3402;
constexpr uint32_t STATUS_ERR_QUOTE_VERIFY_FAIL  = 0xDEAD3403;
constexpr uint32_t STATUS_ERR_POLICY_MISMATCH    = 0xDEAD3404;

#ifdef __clang__
#define DR34_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR34_DISABLE_UNROLL
#endif

// Lightweight Hash & Extend primitive (SHA-256 / Keccak transform model)
__attribute__((noinline)) void hash_extend_pcr(
    uint8_t* pcr_val,
    const uint8_t* measurement
) {
    // PCR[i] = Hash(PCR[i] || Measurement)
    // 32-byte state transformation with round constants
    uint32_t h[8];
    for (int k = 0; k < 8; ++k) {
        h[k] = (reinterpret_cast<const uint32_t*>(pcr_val))[k];
    }

    const uint32_t* m = reinterpret_cast<const uint32_t*>(measurement);
    DR34_DISABLE_UNROLL
    for (int r = 0; r < 8; ++r) {
        uint32_t val = m[r] ^ (0x9E3779B9 + r);
        h[r] = ((h[r] << 7) | (h[r] >> 25)) + val + (h[(r + 1) % 8] ^ 0xA5A5A5A5);
    }

    for (int k = 0; k < 8; ++k) {
        (reinterpret_cast<uint32_t*>(pcr_val))[k] = h[k];
    }
}

// Compute composite PCR digest over selected registers in mask
__attribute__((noinline)) void compute_composite_pcr_digest(
    const uint8_t pcr_bank[PCR_COUNT][32],
    uint32_t pcr_mask,
    uint8_t* composite_digest
) {
    for (int i = 0; i < 32; ++i) {
        composite_digest[i] = 0;
    }

    uint32_t accum[8] = {
        0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
        0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19
    };

    DR34_DISABLE_UNROLL
    for (uint32_t p = 0; p < PCR_COUNT; ++p) {
        if ((pcr_mask & (1U << p)) != 0) {
            const uint32_t* pcr_words = reinterpret_cast<const uint32_t*>(pcr_bank[p]);
            DR34_DISABLE_UNROLL
            for (int k = 0; k < 8; ++k) {
                accum[k] = ((accum[k] << 5) | (accum[k] >> 27)) ^ pcr_words[k] ^ (p + 1);
            }
        }
    }

    for (int k = 0; k < 8; ++k) {
        (reinterpret_cast<uint32_t*>(composite_digest))[k] = accum[k];
    }
}

// Compute TPM 2.0 / DICE TPMS_QUOTE_INFO digest
__attribute__((noinline)) void compute_quote_digest(
    uint32_t pcr_mask,
    const uint8_t* composite_digest,
    const uint8_t* nonce,
    uint8_t* quote_digest
) {
    uint32_t q[8];
    const uint32_t* c = reinterpret_cast<const uint32_t*>(composite_digest);
    const uint32_t* n = reinterpret_cast<const uint32_t*>(nonce);

    DR34_DISABLE_UNROLL
    for (int k = 0; k < 8; ++k) {
        q[k] = c[k] ^ n[k] ^ (pcr_mask + k * 0x1010101);
        q[k] = ((q[k] << 9) | (q[k] >> 23)) + 0x44494345;
    }

    for (int k = 0; k < 8; ++k) {
        (reinterpret_cast<uint32_t*>(quote_digest))[k] = q[k];
    }
}

// Derive CDI (Compound Device Identifier) via KDF(UDS, Measurement)
__attribute__((noinline)) void derive_cdi(
    const uint8_t* uds,
    const uint8_t* measurement,
    uint8_t* cdi_out
) {
    const uint32_t* u = reinterpret_cast<const uint32_t*>(uds);
    const uint32_t* m = reinterpret_cast<const uint32_t*>(measurement);
    uint32_t* out = reinterpret_cast<uint32_t*>(cdi_out);

    DR34_DISABLE_UNROLL
    for (int k = 0; k < 8; ++k) {
        uint32_t t = u[k] ^ m[k];
        out[k] = ((t << 13) | (t >> 19)) ^ (0x5C5C5C5C + k * 0x1F1F1F1F);
    }
}

} // namespace dr34

#endif // DR34_DICE_TPM_INTERNAL_HPP
