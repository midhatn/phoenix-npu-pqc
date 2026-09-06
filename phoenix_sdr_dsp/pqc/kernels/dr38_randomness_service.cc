// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR38: Randomness Statistical Battery & NIST SP 800-22 Diagnostic
 * AMD Phoenix NPU (AIE2 / XDNA1 Architecture) Service Kernel.
 * Dispatched on AIE2 vector compute tiles.
 * Evaluates BSI AIS 31 Test T8 Shannon entropy and NIST SP 800-90B health tests.
 */

#include <stdint.h>
#include <stddef.h>
#include "dr38_randomness_internal.hpp"

extern "C" {

void dr38_randomness_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack 64-byte descriptor header
    uint32_t magic            = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode          = *(const uint32_t*)(descriptor_in + 4);
    uint32_t sample_bytes_len = *(const uint32_t*)(descriptor_in + 8);
    uint32_t block_size       = *(const uint32_t*)(descriptor_in + 12);
    uint32_t flags            = *(const uint32_t*)(descriptor_in + 16);
    uint32_t seq_id           = *(const uint32_t*)(descriptor_in + 32);

    // Zero out initial 640 bytes of result buffer
    DR38_DISABLE_UNROLL
    for (size_t i = 0; i < 640; ++i) {
        result_out[i] = 0;
    }

    // 2. Validate magic header
    if (magic != dr38::MAGIC_HEADER) {
        *(uint32_t*)(result_out + 0) = dr38::STATUS_ERR_INVALID_MAGIC;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = 0; // Outcome: Failure
        *(uint32_t*)(result_out + 12) = 0;
        return;
    }

    // 3. Bound and validate sample length
    size_t effective_len = sample_bytes_len;
    if (effective_len > dr38::REQ_TOTAL_BYTES) {
        effective_len = dr38::REQ_TOTAL_BYTES;
    }
    if (effective_len == 0) {
        *(uint32_t*)(result_out + 0) = dr38::STATUS_ERR_INSUFFICIENT_LEN;
        *(uint32_t*)(result_out + 4) = op_mode;
        *(uint32_t*)(result_out + 8) = 0; // Outcome: Failure
        *(uint32_t*)(result_out + 12) = 0;
        return;
    }

    // 4. Run Statistical Accumulator
    dr38::BatteryStatistics stats;
    dr38::evaluate_sample_battery(request_in, effective_len, &stats);

    // 5. Evaluate outcome per operation mode
    uint32_t outcome = 1;
    uint32_t status = dr38::STATUS_SUCCESS;

    if (op_mode == dr38::MODE_EVAL_MONOBIT) {
        outcome = stats.monobit_pass;
        status = outcome ? dr38::STATUS_SUCCESS : dr38::STATUS_ERR_TEST_FAILED;
    } else if (op_mode == dr38::MODE_EVAL_POKER) {
        outcome = stats.poker_pass;
        status = outcome ? dr38::STATUS_SUCCESS : dr38::STATUS_ERR_TEST_FAILED;
    } else if (op_mode == dr38::MODE_EVAL_RUNS_LONGEST) {
        outcome = (stats.runs_pass && stats.longest_run_pass) ? 1 : 0;
        status = outcome ? dr38::STATUS_SUCCESS : dr38::STATUS_ERR_TEST_FAILED;
    } else if (op_mode == dr38::MODE_EVAL_SHANNON_ENTROPY) {
        outcome = stats.entropy_pass;
        status = outcome ? dr38::STATUS_SUCCESS : dr38::STATUS_ERR_TEST_FAILED;
    } else if (op_mode == dr38::MODE_EVAL_FULL_BATTERY) {
        int all_passed = (stats.monobit_pass && stats.poker_pass && stats.runs_pass &&
                          stats.longest_run_pass && stats.entropy_pass && !stats.health_failure);
        outcome = all_passed ? 1 : 0;
        status = all_passed ? dr38::STATUS_SUCCESS : dr38::STATUS_ERR_TEST_FAILED;
    } else if (op_mode == dr38::MODE_EVAL_HEALTH_TEST) {
        outcome = (stats.health_failure == 0) ? 1 : 0;
        status = (stats.health_failure == 0) ? dr38::STATUS_SUCCESS : dr38::STATUS_ERR_HEALTH_FAILURE;
    }

    uint32_t cycle_est = 450 + (uint32_t)(effective_len / 32);

    // 6. Pack Result Buffer
    *(uint32_t*)(result_out + 0)  = status;
    *(uint32_t*)(result_out + 4)  = op_mode;
    *(uint32_t*)(result_out + 8)  = outcome;
    *(uint32_t*)(result_out + 12) = cycle_est;

    *(uint32_t*)(result_out + 16) = stats.total_ones;
    *(uint32_t*)(result_out + 20) = stats.total_bits;
    *(uint32_t*)(result_out + 24) = stats.total_runs;
    *(uint32_t*)(result_out + 28) = stats.poker_sum_sq;

    *(uint32_t*)(result_out + 32) = stats.longest_run_ones;
    *(uint32_t*)(result_out + 36) = stats.longest_run_zeros;
    *(uint32_t*)(result_out + 40) = stats.health_failure;
    *(uint32_t*)(result_out + 44) = flags;

    // Pack 256 histogram counts (uint16)
    uint16_t* res_hist = (uint16_t*)(result_out + 64);
    DR38_DISABLE_UNROLL
    for (int i = 0; i < 256; ++i) {
        res_hist[i] = stats.histogram[i];
    }

    // Pack test decision flags
    uint32_t* res_flags = (uint32_t*)(result_out + 576);
    res_flags[0] = stats.monobit_pass;
    res_flags[1] = stats.poker_pass;
    res_flags[2] = stats.runs_pass;
    res_flags[3] = stats.longest_run_pass;
    res_flags[4] = stats.entropy_pass;
}

} // extern "C"
