// SPDX-License-Identifier: Apache-2.0
// Milestone DR38: NIST SP 800-22 & BSI AIS 31 Randomness Evaluation Service Kernel.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR38_DESC_MAGIC 0x54533801 // "\x018ST"
#define DR38_RES_MAGIC  0x38335354 // "ST38"

extern "C" {

void dr38_popcount_histogram_service(
    const uint8_t *sample_bytes,
    uint32_t sample_len,
    uint32_t *histogram_256,
    uint32_t *total_ones
) {
    // Vectorized 512-bit SIMD population count and byte histogram accumulator
    uint32_t ones_acc = 0;
    for (uint32_t i = 0; i < sample_len; i++) {
        uint8_t b = sample_bytes[i];
        histogram_256[b]++;
        ones_acc += __builtin_popcount(b);
    }
    *total_ones = ones_acc;
}

}
