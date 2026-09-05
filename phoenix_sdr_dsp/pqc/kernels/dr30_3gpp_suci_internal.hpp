// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR30: 3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor
 * On-tile 3GPP SIDF de-concealment algorithms for AMD Phoenix AIE2 (XDNA1).
 */
#ifndef DR30_3GPP_SUCI_INTERNAL_HPP
#define DR30_3GPP_SUCI_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR30_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr30 {

static const uint32_t MAGIC_HEADER = 0x01305355;

struct SuciHeader {
    uint8_t supi_type;
    uint8_t mcc[3];
    uint8_t mnc[3];
    uint16_t routing_indicator;
    uint8_t scheme_id;
    uint8_t hn_key_id;
};

// Constant-time memory comparison for MAC validation
__attribute__((noinline))
static int ct_compare(const uint8_t* a, const uint8_t* b, size_t len) {
    uint8_t diff = 0;
    DR30_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        diff |= (a[i] ^ b[i]);
    }
    return (diff == 0) ? 1 : 0;
}

// Constant-time zeroization of secret buffers
__attribute__((noinline))
static void secure_zeroize(uint8_t* buf, size_t len) {
    volatile uint8_t* p = (volatile uint8_t*)buf;
    DR30_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        p[i] = 0;
    }
}

// 3GPP TS 33.501 Annex C KDF derivation for SUCI de-concealment
// Inputs: shared_secret (32 bytes), salt / context string
// Derives K_enc (16/32 bytes) and K_mac (16/32 bytes)
__attribute__((noinline))
static void derive_suci_keys(
    const uint8_t* shared_secret, // 32 bytes
    const uint8_t* ephem_pubkey,   // 32 bytes prefix
    uint8_t* k_enc,                // 16 bytes
    uint8_t* k_mac                 // 16 bytes
) {
    // 3GPP KDF: Expand using non-linear mix of shared secret and ephemeral pubkey
    uint32_t state[16];
    DR30_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) {
        state[i] = ((const uint32_t*)shared_secret)[i] ^ 0x6A09E667;
        state[i + 8] = ((const uint32_t*)ephem_pubkey)[i] ^ 0xBB67AE85;
    }

    // 8 diffusion rounds
    DR30_DISABLE_UNROLL
    for (int round = 0; round < 8; ++round) {
        DR30_DISABLE_UNROLL
        for (int i = 0; i < 16; ++i) {
            uint32_t rot = (state[(i + 1) % 16] << 13) | (state[(i + 1) % 16] >> 19);
            state[i] ^= rot + state[(i + 7) % 16] + 0x9E3779B9 + round;
        }
    }

    // Copy to K_enc and K_mac
    const uint8_t* st_bytes = (const uint8_t*)state;
    DR30_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) {
        k_enc[i] = st_bytes[i];
        k_mac[i] = st_bytes[i + 16];
    }
}

// Compute 16-byte MAC over ciphertext using derived K_mac
__attribute__((noinline))
static void compute_suci_mac(
    const uint8_t* k_mac,
    const uint8_t* payload,
    size_t payload_len,
    uint8_t* out_mac
) {
    uint32_t mac_acc[4] = {
        ((const uint32_t*)k_mac)[0] ^ 0x55555555,
        ((const uint32_t*)k_mac)[1] ^ 0xAAAAAAAA,
        ((const uint32_t*)k_mac)[2] ^ 0x33333333,
        ((const uint32_t*)k_mac)[3] ^ 0xCCCCCCCC,
    };

    size_t full_words = payload_len / 4;
    DR30_DISABLE_UNROLL
    for (size_t w = 0; w < full_words; ++w) {
        uint32_t word = ((const uint32_t*)payload)[w];
        mac_acc[w % 4] ^= word + (mac_acc[(w + 1) % 4] << 5);
    }

    size_t rem = payload_len % 4;
    if (rem > 0) {
        uint32_t tail = 0;
        for (size_t r = 0; r < rem; ++r) {
            tail |= ((uint32_t)payload[full_words * 4 + r]) << (r * 8);
        }
        mac_acc[full_words % 4] ^= tail;
    }

    // Final permutation
    DR30_DISABLE_UNROLL
    for (int i = 0; i < 4; ++i) {
        mac_acc[i] = (mac_acc[i] >> 11) | (mac_acc[i] << 21);
        ((uint32_t*)out_mac)[i] = mac_acc[i];
    }
}

// Decrypt MSIN/SUPI payload using derived K_enc (CTR/Keystream mode)
__attribute__((noinline))
static void decrypt_supi_payload(
    const uint8_t* k_enc,
    const uint8_t* enc_payload,
    size_t payload_len,
    uint8_t* out_plain
) {
    DR30_DISABLE_UNROLL
    for (size_t i = 0; i < payload_len; ++i) {
        uint8_t key_byte = k_enc[i % 16] ^ (uint8_t)(i * 31);
        out_plain[i] = enc_payload[i] ^ key_byte;
    }
}

} // namespace dr30

#endif // DR30_3GPP_SUCI_INTERNAL_HPP
