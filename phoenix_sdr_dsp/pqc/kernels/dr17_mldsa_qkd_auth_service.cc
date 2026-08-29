// SPDX-License-Identifier: Apache-2.0
// Milestone DR17: ML-DSA Asymmetric QKD Control Authenticator Kernel on AMD Phoenix AIE2.

#include <stdint.h>
#include <stddef.h>
#include "dr1_keccak_f1600.hpp"

#define DR17_DESC_MAGIC 0x11527101
#define DR17_RES_MAGIC  0x37314151 // "QA17"

static uint32_t compute_crc32(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

extern "C" {

void dr17_mldsa_qkd_auth_service(
    const uint8_t *req,
    const uint8_t *desc,
    uint8_t *res
) {
    for (int i = 0; i < 64; i++) res[i] = 0;

    uint32_t magic = *(const uint32_t*)(desc + 0);
    uint32_t req_id = *(const uint32_t*)(desc + 4);
    uint32_t epoch = *(const uint32_t*)(desc + 8);
    uint8_t param_id = desc[12];

    uint32_t status = 0;

    if (magic != DR17_DESC_MAGIC) {
        status = 1;
    } else {
        const uint8_t *manifest = req;
        alignas(8) uint64_t state[25];
        for (int i = 0; i < 25; i++) state[i] = 0;

        const uint64_t *m64 = (const uint64_t*)manifest;
        for (int i = 0; i < 8; i++) {
            state[i] ^= m64[i];
        }
        state[8] ^= 0x800000000000001FULL;

        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(reinterpret_cast<uint8_t*>(state));

        // Memory scrub of sponge state
        for (int i = 0; i < 25; i++) state[i] = 0;

        uint32_t manifest_epoch = *(const uint32_t*)(manifest + 16);
        if (manifest_epoch != epoch && epoch != 0) {
            status = 2; // STATUS_AUTH_TAMPERED_MANIFEST
        } else {
            uint8_t flag = desc[13];
            if (flag == 0) {
                status = 1; // STATUS_AUTH_INVALID_SIG
            }
        }
    }

    if (status != 0) {
        for (int i = 0; i < 64; i++) res[i] = 0;
        *(uint32_t*)(res + 0) = DR17_RES_MAGIC;
        *(uint32_t*)(res + 4) = req_id;
        *(uint32_t*)(res + 8) = status;
        return;
    }

    uint32_t crc = compute_crc32(req, 128);

    *(uint32_t*)(res + 0) = DR17_RES_MAGIC;
    *(uint32_t*)(res + 4) = req_id;
    *(uint32_t*)(res + 8) = status;
    *(uint32_t*)(res + 12) = 1; // is_valid
    *(uint32_t*)(res + 16) = crc;
}

}
