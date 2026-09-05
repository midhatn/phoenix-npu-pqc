// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR40: High-Throughput Hardware Benchmark Protocol & Profiling Battery
 * AMD Phoenix NPU (AIE2 / XDNA1 Architecture) Service Kernel.
 * Dispatched on AIE2 vector compute tiles.
 */

#include <stdint.h>
#include <stddef.h>
#include "dr40_benchmark_internal.hpp"

extern "C" {

void dr40_benchmark_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack 64-byte descriptor header
    uint32_t magic         = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode       = *(const uint32_t*)(descriptor_in + 4);
    uint32_t batch_size    = *(const uint32_t*)(descriptor_in + 8);
    uint32_t warmup_iters  = *(const uint32_t*)(descriptor_in + 12);
    uint32_t flags         = *(const uint32_t*)(descriptor_in + 16);
    uint32_t param_0       = *(const uint32_t*)(descriptor_in + 20);
    uint32_t param_1       = *(const uint32_t*)(descriptor_in + 24);
    uint32_t seq_id        = *(const uint32_t*)(descriptor_in + 32);

    // Zero out initial 544 bytes of result buffer (32 header + 512 payload)
    DR40_DISABLE_UNROLL
    for (size_t i = 0; i < 544; ++i) {
        result_out[i] = 0;
    }

    // 2. Validate magic header
    if (magic != dr40::MAGIC_HEADER) {
        *(uint32_t*)(result_out + 0) = dr40::STATUS_ERR_INVALID_MAGIC;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = batch_size;
        *(uint32_t*)(result_out + 12) = 0;
        *(uint32_t*)(result_out + 16) = 0;
        return;
    }

    // 3. Validate batch size
    if (batch_size == 0) {
        *(uint32_t*)(result_out + 0) = dr40::STATUS_ERR_INVALID_BATCH;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 0;
        *(uint32_t*)(result_out + 16) = 0;
        return;
    }

    uint32_t total_iters = warmup_iters + batch_size;
    uint32_t checksum = 0;

    // 4. Dispatch workload based on op_mode
    if (op_mode == dr40::MODE_BENCH_NTT_BUTTERFLY) {
        uint16_t poly[256];
        const uint16_t* in_poly = (const uint16_t*)request_in;
        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 256; ++i) {
            poly[i] = (uint16_t)(in_poly[i] % dr40::MODULUS_Q);
        }

        uint32_t twiddle = 1753; // Standard twiddle factor
        DR40_DISABLE_UNROLL
        for (uint32_t it = 0; it < total_iters; ++it) {
            dr40::ntt_butterfly_layer(poly, twiddle);
            twiddle = (twiddle * 17u) % dr40::MODULUS_Q;
            if (twiddle == 0) {
                twiddle = 1;
            }
        }

        uint16_t* out_poly = (uint16_t*)(result_out + 32);
        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 256; ++i) {
            out_poly[i] = poly[i];
            checksum = (checksum + poly[i]) & 0xFFFFFFFFu;
        }

    } else if (op_mode == dr40::MODE_BENCH_KECCAK_F1600) {
        uint64_t state[25];
        const uint64_t* in_state = (const uint64_t*)request_in;
        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 25; ++i) {
            state[i] = in_state[i];
        }

        uint32_t rounds = (param_0 > 0 && param_0 <= 24) ? param_0 : 24;
        DR40_DISABLE_UNROLL
        for (uint32_t it = 0; it < total_iters; ++it) {
            DR40_DISABLE_UNROLL
            for (uint32_t r = 0; r < rounds; ++r) {
                dr40::keccak_round(state, r);
            }
        }

        uint64_t* out_state = (uint64_t*)(result_out + 32);
        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 25; ++i) {
            out_state[i] = state[i];
            checksum = (checksum + (uint32_t)(state[i] & 0xFFFFFFFFu) + (uint32_t)(state[i] >> 32)) & 0xFFFFFFFFu;
        }

    } else if (op_mode == dr40::MODE_BENCH_VECTOR_MAC) {
        uint16_t poly_a[256];
        uint16_t poly_b[256];
        uint16_t accum[256];
        const uint16_t* in_a = (const uint16_t*)request_in;
        const uint16_t* in_b = (const uint16_t*)(request_in + 512);

        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 256; ++i) {
            poly_a[i] = (uint16_t)(in_a[i] % dr40::MODULUS_Q);
            poly_b[i] = (uint16_t)(in_b[i] % dr40::MODULUS_Q);
            accum[i] = 0;
        }

        DR40_DISABLE_UNROLL
        for (uint32_t it = 0; it < total_iters; ++it) {
            dr40::vector_mac_step(accum, poly_a, poly_b);
            DR40_DISABLE_UNROLL
            for (size_t i = 0; i < 256; ++i) {
                poly_b[i] = (uint16_t)(((uint32_t)poly_b[i] + 3u) % dr40::MODULUS_Q);
            }
        }

        uint16_t* out_accum = (uint16_t*)(result_out + 32);
        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 256; ++i) {
            out_accum[i] = accum[i];
            checksum = (checksum + accum[i]) & 0xFFFFFFFFu;
        }

    } else if (op_mode == dr40::MODE_BENCH_SAMPLE_NTT) {
        uint16_t coeffs[256];
        dr40::sample_ntt(request_in, 768, coeffs);

        DR40_DISABLE_UNROLL
        for (uint32_t it = 0; it < total_iters; ++it) {
            DR40_DISABLE_UNROLL
            for (size_t i = 0; i < 256; ++i) {
                coeffs[i] = (uint16_t)(((uint32_t)coeffs[i] * 3u + 7u) % dr40::MODULUS_Q);
            }
        }

        uint16_t* out_coeffs = (uint16_t*)(result_out + 32);
        DR40_DISABLE_UNROLL
        for (size_t i = 0; i < 256; ++i) {
            out_coeffs[i] = coeffs[i];
            checksum = (checksum + coeffs[i]) & 0xFFFFFFFFu;
        }

    } else {
        *(uint32_t*)(result_out + 0) = dr40::STATUS_ERR_UNSUPPORTED_MODE;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = batch_size;
        *(uint32_t*)(result_out + 12) = 0;
        *(uint32_t*)(result_out + 16) = 0;
        return;
    }

    // 5. Finalize result header
    *(uint32_t*)(result_out + 0)  = dr40::STATUS_SUCCESS;
    *(uint32_t*)(result_out + 4)  = op_mode;
    *(uint32_t*)(result_out + 8)  = batch_size;
    *(uint32_t*)(result_out + 12) = total_iters;
    *(uint32_t*)(result_out + 16) = checksum;
}

} // extern "C"
