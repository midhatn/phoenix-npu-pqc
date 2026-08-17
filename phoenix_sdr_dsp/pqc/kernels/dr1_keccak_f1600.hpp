// SPDX-License-Identifier: Apache-2.0
// Production-local Keccak-f[1600] used only by DR1 SHAKE128.
//
// This is a compact structural implementation of FIPS 202 Keccak-p[1600,24]:
// https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
// It deliberately derives Iota constants with the FIPS LFSR and follows the
// Rho/Pi orbit, rather than placing round data in static read-only storage.
// That layout is the v3 repair for the v2 first-block Phoenix silicon mismatch.
#pragma once

#include <cstdint>

// Phoenix AIE builds use Clang. Keep the loop-control spelling local so host
// g++ syntax checks remain strict while AIE compilation receives the same
// disabled-unroll protection as the proven M32c Keccak implementation.
#if defined(__clang__)
#define DR1_AIE_DISABLE_LOOP_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR1_AIE_DISABLE_LOOP_UNROLL
#endif

namespace phoenix_sdr_dsp::pqc::dr1 {

static inline uint64_t rol64(uint64_t value, unsigned int shift) {
    // The Rho/Pi orbit never uses a zero rotation.
    return (value << shift) | (value >> (64u - shift));
}

// FIPS 202 Algorithm 5's 8-bit LFSR for the seven Iota bits per round.
static inline int lfsr86540(uint8_t *lfsr) {
    const int result = ((*lfsr) & 0x01) != 0;
    if (((*lfsr) & 0x80) != 0) {
        *lfsr = static_cast<uint8_t>(((*lfsr) << 1) ^ 0x71);
    } else {
        *lfsr = static_cast<uint8_t>((*lfsr) << 1);
    }
    return result;
}

// Do not inline this 24-round permutation into the SHAKE dispatcher. Phoenix
// AIE2 has a 16 KiB program-memory constraint, and compiler-reported program
// size remains the authoritative physical acceptance artifact.
//
// state points to an explicitly 8-byte-aligned, little-endian 200-byte state.
// The byte representation and compact recurrence intentionally match the
// physically proven M32c algorithm structure while remaining source-local.
__attribute__((noinline)) static void keccak_f1600(uint8_t *state) {
    uint64_t *A = reinterpret_cast<uint64_t *>(state);
    uint8_t lfsr = 0x01;

    DR1_AIE_DISABLE_LOOP_UNROLL
    for (int round = 0; round < 24; ++round) {
        const uint64_t C0 = A[0] ^ A[5] ^ A[10] ^ A[15] ^ A[20];
        const uint64_t C1 = A[1] ^ A[6] ^ A[11] ^ A[16] ^ A[21];
        const uint64_t C2 = A[2] ^ A[7] ^ A[12] ^ A[17] ^ A[22];
        const uint64_t C3 = A[3] ^ A[8] ^ A[13] ^ A[18] ^ A[23];
        const uint64_t C4 = A[4] ^ A[9] ^ A[14] ^ A[19] ^ A[24];
        const uint64_t D0 = C4 ^ rol64(C1, 1);
        const uint64_t D1 = C0 ^ rol64(C2, 1);
        const uint64_t D2 = C1 ^ rol64(C3, 1);
        const uint64_t D3 = C2 ^ rol64(C4, 1);
        const uint64_t D4 = C3 ^ rol64(C0, 1);
        A[0] ^= D0; A[5] ^= D0; A[10] ^= D0; A[15] ^= D0; A[20] ^= D0;
        A[1] ^= D1; A[6] ^= D1; A[11] ^= D1; A[16] ^= D1; A[21] ^= D1;
        A[2] ^= D2; A[7] ^= D2; A[12] ^= D2; A[17] ^= D2; A[22] ^= D2;
        A[3] ^= D3; A[8] ^= D3; A[13] ^= D3; A[18] ^= D3; A[23] ^= D3;
        A[4] ^= D4; A[9] ^= D4; A[14] ^= D4; A[19] ^= D4; A[24] ^= D4;

        // Rho/Pi: walk the FIPS (1,0) orbit with r_t=(t+1)(t+2)/2 mod 64.
        {
            unsigned int x = 1;
            unsigned int y = 0;
            uint64_t current = A[1 + 5 * 0];
            DR1_AIE_DISABLE_LOOP_UNROLL
            for (int t = 0; t < 24; ++t) {
                const unsigned int r_off =
                    (((unsigned int)(t + 1) * (unsigned int)(t + 2)) / 2u) % 64u;
                const unsigned int Y = (2u * x + 3u * y) % 5u;
                x = y;
                y = Y;
                const unsigned int index = x + 5u * y;
                const uint64_t temporary = A[index];
                A[index] = rol64(current, r_off);
                current = temporary;
            }
        }

        DR1_AIE_DISABLE_LOOP_UNROLL
        for (int y = 0; y < 5; ++y) {
            const uint64_t t0 = A[0 + 5 * y];
            const uint64_t t1 = A[1 + 5 * y];
            const uint64_t t2 = A[2 + 5 * y];
            const uint64_t t3 = A[3 + 5 * y];
            const uint64_t t4 = A[4 + 5 * y];
            A[0 + 5 * y] = t0 ^ ((~t1) & t2);
            A[1 + 5 * y] = t1 ^ ((~t2) & t3);
            A[2 + 5 * y] = t2 ^ ((~t3) & t4);
            A[3 + 5 * y] = t3 ^ ((~t4) & t0);
            A[4 + 5 * y] = t4 ^ ((~t0) & t1);
        }

        uint64_t round_constant = 0;
        DR1_AIE_DISABLE_LOOP_UNROLL
        for (int j = 0; j < 7; ++j) {
            const unsigned int bit_position = (1u << j) - 1u;
            if (lfsr86540(&lfsr)) {
                round_constant ^= (static_cast<uint64_t>(1) << bit_position);
            }
        }
        A[0] ^= round_constant;
    }
}

}  // namespace phoenix_sdr_dsp::pqc::dr1
