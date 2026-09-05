// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR33: Physical Side-Channel Power/EM Trace Acquisition & TVLA Framework
 * Internal Header for AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#ifndef DR33_SIDE_CHANNEL_TVLA_INTERNAL_HPP
#define DR33_SIDE_CHANNEL_TVLA_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

namespace dr33 {

// Magic Header: "TVLA" in ASCII (0x54564C41)
constexpr uint32_t MAGIC_HEADER = 0x54564C41;

// Operation Modes
constexpr uint32_t MODE_TVLA_TRIGGER_EMIT     = 0x01; // Hardware trigger marker emission
constexpr uint32_t MODE_TVLA_FIXED_VS_RANDOM  = 0x02; // Fixed vs pseudo-random execution sequence
constexpr uint32_t MODE_TVLA_CALIBRATION_PULSE= 0x03; // Alignment calibration pulse train
constexpr uint32_t MODE_TVLA_MASKED_PIPELINE  = 0x04; // Masked polynomial pipeline execution

// Target Algorithm Identifiers
constexpr uint32_t TARGET_ML_KEM_NTT          = 0x01; // NTT polynomial arithmetic
constexpr uint32_t TARGET_ML_DSA_POLY         = 0x02; // ML-DSA polynomial operations
constexpr uint32_t TARGET_KECCAK_F1600        = 0x03; // Keccak-f[1600] state transform
constexpr uint32_t TARGET_MASKED_MULT         = 0x04; // Masked polynomial multiplication

// Trigger Phase Markers
constexpr uint32_t PHASE_IDLE                 = 0x00;
constexpr uint32_t PHASE_START_TRIGGER        = 0x01;
constexpr uint32_t PHASE_PRE_EXECUTION        = 0x02;
constexpr uint32_t PHASE_CORE_COMPUTE         = 0x03;
constexpr uint32_t PHASE_POST_EXECUTION       = 0x04;
constexpr uint32_t PHASE_STOP_TRIGGER         = 0x05;

// Status Flags
constexpr uint32_t STATUS_SUCCESS             = 0x00000000;
constexpr uint32_t STATUS_ERR_INVALID_MAGIC   = 0xDEAD0033;
constexpr uint32_t STATUS_ERR_UNKNOWN_MODE    = 0xDEAD0034;
constexpr uint32_t STATUS_ERR_UNKNOWN_TARGET  = 0xDEAD0035;

// Standard Polynomial Modulus for ML-KEM
constexpr int32_t Q_MLKEM = 3329;

// Montgomery Reduction Constant
constexpr int32_t Q_INV = 62209; // -q^{-1} mod 2^16

inline int16_t montgomery_reduce(int32_t a) {
    int16_t t = (int16_t)((int32_t)(int16_t)a * (int32_t)Q_INV);
    int32_t res = (a - (int32_t)t * (int32_t)Q_MLKEM) >> 16;
    return (int16_t)res;
}

inline int16_t barrett_reduce(int16_t a) {
    int32_t t = ((int32_t)a * 20159) >> 26;
    int16_t res = (int16_t)(a - (int16_t)(t * Q_MLKEM));
    return res;
}

// Compute a deterministic polynomial transform under TVLA observation
inline void compute_polynomial_workload(
    uint32_t target_algo,
    const uint8_t* in_vec,
    uint32_t in_len,
    uint8_t* out_vec,
    uint32_t* out_accum
) {
    uint32_t accum = 0;
    const uint16_t* in16 = reinterpret_cast<const uint16_t*>(in_vec);
    uint16_t* out16 = reinterpret_cast<uint16_t*>(out_vec);
    uint32_t num_coeffs = (in_len >= 512) ? 256 : (in_len / 2);
    if (num_coeffs == 0) num_coeffs = 256;

    for (uint32_t i = 0; i < num_coeffs; ++i) {
        uint16_t coeff = in16[i % (in_len / 2 > 0 ? (in_len / 2) : 1)];

        if (target_algo == TARGET_ML_KEM_NTT) {
            // Butterfly multiplication simulation step with twiddle factor
            int16_t twiddle = static_cast<int16_t>((i * 17 + 1) % Q_MLKEM);
            int32_t prod = (int32_t)static_cast<int16_t>(coeff) * (int32_t)twiddle;
            int16_t reduced = montgomery_reduce(prod);
            out16[i] = static_cast<uint16_t>(barrett_reduce(reduced));
            accum += static_cast<uint32_t>(out16[i]);
        } else if (target_algo == TARGET_ML_DSA_POLY) {
            // Positive modulus reduction for ML-DSA (q = 8380417)
            uint32_t val = (static_cast<uint32_t>(coeff) * 3 + 7) % 8380417;
            out16[i] = static_cast<uint16_t>(val);
            accum ^= static_cast<uint32_t>(out16[i]);
        } else if (target_algo == TARGET_MASKED_MULT) {
            // Two-share masked addition & refresh step
            uint16_t mask = static_cast<uint16_t>((i * 0x9E37) ^ 0x55AA);
            uint16_t share0 = coeff ^ mask;
            uint16_t share1 = mask;
            out16[i] = share0 ^ share1; // Unmasked recombination
            accum += out16[i];
        } else {
            // Keccak round step transform with logical rotation
            uint16_t rotated = static_cast<uint16_t>((coeff << 5) | (coeff >> 11));
            out16[i] = rotated ^ 0x96;
            accum = (accum << 1) ^ out16[i];
        }
    }

    if (out_accum) {
        *out_accum = accum;
    }
}

} // namespace dr33

#endif // DR33_SIDE_CHANNEL_TVLA_INTERNAL_HPP
