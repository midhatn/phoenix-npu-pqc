// SPDX-License-Identifier: Apache-2.0
// Milestone DR42: ANSSI Composite & Dual-Signature Sovereign Standard Kernel.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR42_DESC_MAGIC 0x53434201 // "\x01BCS"
#define DR42_RES_MAGIC  0x42534342 // "CS42"

extern "C" {

void dr42_atomic_conjunction_service(
    uint32_t trad_valid_flag,
    uint32_t pqc_valid_flag,
    uint32_t *out_composite_valid_flag
) {
    // Constant-time atomic boolean conjunction: (trad_valid == 1) & (pqc_valid == 1)
    *out_composite_valid_flag = (trad_valid_flag & pqc_valid_flag) & 1;
}

}
