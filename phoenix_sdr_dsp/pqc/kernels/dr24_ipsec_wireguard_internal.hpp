// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR24: RFC 9370 Multi-KEM IPsec / WireGuard Inline VPN Co-Processor
 * Micro-architecture and cryptographic primitives for AMD Phoenix AIE2 (XDNA1).
 */
#ifndef DR24_IPSEC_WIREGUARD_INTERNAL_HPP
#define DR24_IPSEC_WIREGUARD_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>
#include "dr1_keccak_f1600.hpp"

#define DR24_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr24 {

__attribute__((noinline))
static void shake256_stream(
    const uint8_t* in,
    size_t in_len,
    uint8_t* out,
    size_t out_len
) {
    alignas(8) uint8_t state[200];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 200; ++i) state[i] = 0;

    const size_t rate = 136;
    size_t spos = 0;

    DR24_DISABLE_UNROLL
    for (size_t i = 0; i < in_len; ++i) {
        state[spos++] ^= in[i];
        if (spos == rate) {
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
            spos = 0;
        }
    }

    // FIPS 202 SHAKE-256 domain separator (0x1F) and padding
    state[spos] ^= 0x1Fu;
    state[rate - 1] ^= 0x80u;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

    // Squeeze output bytes
    size_t squeezed = 0;
    while (squeezed < out_len) {
        size_t take = (out_len - squeezed < rate) ? (out_len - squeezed) : rate;
        DR24_DISABLE_UNROLL
        for (size_t i = 0; i < take; ++i) {
            out[squeezed + i] = state[i];
        }
        squeezed += take;
        if (squeezed < out_len) {
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
        }
    }
}

// RFC 9370 Multi-KEM Key Derivation Combiner
__attribute__((noinline))
static void rfc9370_combine_keys(
    const uint8_t* k_classic,   // 32 bytes
    const uint8_t* k_pqc,       // 32 bytes
    const uint8_t* k_qkd,       // 32 bytes (optional, 0 if unused)
    const uint8_t* ni_nr,       // 64 bytes nonces (Ni || Nr)
    uint8_t* out_ske,           // 32 bytes (Tunnel Encrypt)
    uint8_t* out_ska,           // 32 bytes (Tunnel Auth)
    uint8_t* out_skd            // 32 bytes (Next Rekey Derivation)
) {
    uint8_t combo[160];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) combo[i] = k_classic[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) combo[32 + i] = k_pqc[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) combo[64 + i] = k_qkd[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) combo[96 + i] = ni_nr[i];

    uint8_t derived[96];
    shake256_stream(combo, 160, derived, 96);

    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) {
        out_ske[i] = derived[i];
        out_ska[i] = derived[32 + i];
        out_skd[i] = derived[64 + i];
    }
}

// WireGuard Packet Encapsulation
__attribute__((noinline))
static void wireguard_encapsulate(
    const uint8_t* ske,
    const uint8_t* ska,
    uint64_t seq_num,
    const uint8_t* plaintext,
    size_t payload_len,
    uint8_t* out_packet,  // 8 bytes seq + 16 bytes tag + payload_len bytes ct
    size_t* out_packet_len
) {
    // 1. Pack sequence number (8 bytes little-endian)
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) {
        out_packet[i] = (uint8_t)((seq_num >> (8 * i)) & 0xFF);
    }

    // 2. Generate keystream and encrypt payload
    uint8_t key_seed[40];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) key_seed[i] = ske[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) key_seed[32 + i] = out_packet[i];

    uint8_t keystream[1500];
    size_t ct_len = (payload_len <= 1500) ? payload_len : 1500;
    shake256_stream(key_seed, 40, keystream, ct_len);

    DR24_DISABLE_UNROLL
    for (size_t i = 0; i < ct_len; ++i) {
        out_packet[24 + i] = plaintext[i] ^ keystream[i];
    }

    // 3. Compute 16-byte authentication tag over (ska || seq_num || ciphertext)
    uint8_t auth_input[1544];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) auth_input[i] = ska[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) auth_input[32 + i] = out_packet[i];
    DR24_DISABLE_UNROLL
    for (size_t i = 0; i < ct_len; ++i) auth_input[40 + i] = out_packet[24 + i];

    uint8_t tag[16];
    shake256_stream(auth_input, 40 + ct_len, tag, 16);
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) {
        out_packet[8 + i] = tag[i];
    }

    *out_packet_len = 24 + ct_len;
}

// WireGuard Packet Decapsulation
__attribute__((noinline))
static int wireguard_decapsulate(
    const uint8_t* ske,
    const uint8_t* ska,
    const uint8_t* packet,
    size_t packet_len,
    uint64_t* out_seq_num,
    uint8_t* out_plaintext,
    size_t* out_payload_len
) {
    if (packet_len < 24) return 1; // Packet too short
    size_t ct_len = packet_len - 24;

    // 1. Extract sequence number
    uint64_t seq = 0;
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) {
        seq |= ((uint64_t)packet[i]) << (8 * i);
    }
    *out_seq_num = seq;

    // 2. Verify authentication tag
    uint8_t auth_input[1544];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) auth_input[i] = ska[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) auth_input[32 + i] = packet[i];
    DR24_DISABLE_UNROLL
    for (size_t i = 0; i < ct_len; ++i) auth_input[40 + i] = packet[24 + i];

    uint8_t expected_tag[16];
    shake256_stream(auth_input, 40 + ct_len, expected_tag, 16);

    uint8_t diff = 0;
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) {
        diff |= (packet[8 + i] ^ expected_tag[i]);
    }
    if (diff != 0) return 2; // Authentication failure

    // 3. Decrypt payload
    uint8_t key_seed[40];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) key_seed[i] = ske[i];
    DR24_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) key_seed[32 + i] = packet[i];

    uint8_t keystream[1500];
    shake256_stream(key_seed, 40, keystream, ct_len);

    DR24_DISABLE_UNROLL
    for (size_t i = 0; i < ct_len; ++i) {
        out_plaintext[i] = packet[24 + i] ^ keystream[i];
    }
    *out_payload_len = ct_len;
    return 0; // Success
}

} // namespace dr24

#endif // DR24_IPSEC_WIREGUARD_INTERNAL_HPP
