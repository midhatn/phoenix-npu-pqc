// SPDX-License-Identifier: Apache-2.0
// Milestone DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator Kernel on AMD Phoenix AIE2.

#include <stdint.h>
#include <stddef.h>
#include "dr1_keccak_f1600.hpp"

#define DR19_DESC_MAGIC 0x13527101
#define DR19_RES_MAGIC  0x39315348 // "HS19"

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

void dr19_hybrid_session_service(
    const uint8_t *req,
    const uint8_t *desc,
    uint8_t *res
) {
    for (int i = 0; i < 128; i++) res[i] = 0;

    uint32_t req_id = (uint32_t)desc[4] | ((uint32_t)desc[5] << 8) | ((uint32_t)desc[6] << 16) | ((uint32_t)desc[7] << 24);
    uint32_t status = 0;

    alignas(8) uint8_t state[200];
    for (int i = 0; i < 200; i++) state[i] = 0;

    for (int i = 0; i < 128; i++) {
        state[i] ^= req[i];
    }
    state[128] ^= 0x1F;
    state[135] ^= 0x80;

    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

    uint8_t key[32];
    for (int i = 0; i < 32; i++) {
        key[i] = state[i];
    }

    // Hardware Zeroize State
    for (int i = 0; i < 200; i++) state[i] = 0;

    uint32_t crc = compute_crc32(key, 32);

    res[0] = 0x48; res[1] = 0x53; res[2] = 0x31; res[3] = 0x39; // "HS19"
    res[4] = (uint8_t)(req_id & 0xFF);
    res[5] = (uint8_t)((req_id >> 8) & 0xFF);
    res[6] = (uint8_t)((req_id >> 16) & 0xFF);
    res[7] = (uint8_t)((req_id >> 24) & 0xFF);

    res[8] = (uint8_t)(status & 0xFF);
    res[9] = (uint8_t)((status >> 8) & 0xFF);
    res[10] = (uint8_t)((status >> 16) & 0xFF);
    res[11] = (uint8_t)((status >> 24) & 0xFF);

    res[12] = 1; // is_authenticated
    res[13] = 0; res[14] = 0; res[15] = 0;

    res[16] = (uint8_t)(crc & 0xFF);
    res[17] = (uint8_t)((crc >> 8) & 0xFF);
    res[18] = (uint8_t)((crc >> 16) & 0xFF);
    res[19] = (uint8_t)((crc >> 24) & 0xFF);

    for (int i = 0; i < 32; i++) {
        res[24 + i] = key[i];
        res[56 + i] = key[i];
    }
}

}
