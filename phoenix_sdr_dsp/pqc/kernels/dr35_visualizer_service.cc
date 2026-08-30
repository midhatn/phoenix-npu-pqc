// SPDX-License-Identifier: Apache-2.0
// Milestone DR35: Real-Time AIE2 Microcode Telemetry Probe Kernel.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR35_DESC_MAGIC 0x49563501 // "\x015VI"
#define DR35_RES_MAGIC  0x35334956 // "VI35"

extern "C" {

void dr35_telemetry_probe_service(
    uint32_t col,
    uint32_t row,
    uint32_t cycle_lo,
    uint32_t cycle_hi,
    uint32_t sram_high_watermark,
    uint8_t *out_record
) {
    *(uint32_t*)(out_record + 0)  = DR35_RES_MAGIC;
    *(uint32_t*)(out_record + 4)  = col;
    *(uint32_t*)(out_record + 8)  = row;
    *(uint32_t*)(out_record + 12) = cycle_lo;
    *(uint32_t*)(out_record + 16) = cycle_hi;
    *(uint32_t*)(out_record + 20) = sram_high_watermark;
}

}
