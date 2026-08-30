// SPDX-License-Identifier: Apache-2.0
// Milestone DR34: On-Device Firmware Remote Attestation Service Kernel.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR34_DESC_MAGIC 0x49443401 // "\x014DI"
#define DR34_RES_MAGIC  0x34334449 // "DI34"

extern "C" {

void dr34_pcr_extend_service(
    const uint8_t *old_pcr,
    const uint8_t *new_measurement,
    uint8_t *out_pcr
) {
    // Hardware SHA-256 state extension simulation
    uint32_t acc = 0x6a09e667;
    for (int i = 0; i < 32; i++) {
        out_pcr[i] = old_pcr[i] ^ new_measurement[i] ^ ((acc >> (i % 4)) & 0xFF);
    }
}

}
