// SPDX-License-Identifier: Apache-2.0
// Milestone DR39: dudect Microarchitectural Side-Channel TVLA Kernel Service.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR39_DESC_MAGIC 0x55443901 // "\x019DU"
#define DR39_RES_MAGIC  0x39334455 // "DU39"

extern "C" {

void dr39_welford_accumulator_service(
    uint64_t new_cycle_sample,
    uint32_t *count,
    double *mean,
    double *m2
) {
    // Welford one-pass mean and variance accumulator on AIE2 vector tile
    (*count)++;
    double x = (double)new_cycle_sample;
    double delta = x - *mean;
    *mean += delta / (*count);
    double delta2 = x - *mean;
    *m2 += delta * delta2;
}

}
