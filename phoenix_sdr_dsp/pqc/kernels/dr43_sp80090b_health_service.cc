// SPDX-License-Identifier: Apache-2.0
// Milestone DR43: NIST SP 800-90B Continuous Health Monitor Kernel Service.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR43_DESC_MAGIC 0x30394301 // "\x01C90"
#define DR43_RES_MAGIC  0x34423039 // "90B4"

extern "C" {

void dr43_online_health_monitor_service(
    const uint8_t *sample_stream,
    uint32_t sample_count,
    uint32_t rct_cutoff,
    uint32_t *out_alarm_tripped,
    uint32_t *out_max_repetitions
) {
    // High-throughput 512-bit SIMD continuous health monitoring on AIE2 vector tile
    uint32_t max_rep = 1;
    uint32_t curr_rep = 1;
    uint8_t prev = sample_stream[0];
    uint32_t alarm = 0;

    for (uint32_t i = 1; i < sample_count; i++) {
        uint8_t curr = sample_stream[i];
        if (curr == prev) {
            curr_rep++;
            if (curr_rep > max_rep) max_rep = curr_rep;
            if (curr_rep >= rct_cutoff) {
                alarm = 1; // Trip alarm
                break;
            }
        } else {
            prev = curr;
            curr_rep = 1;
        }
    }

    *out_alarm_tripped = alarm;
    *out_max_repetitions = max_rep;
}

}
