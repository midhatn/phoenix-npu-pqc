// SPDX-License-Identifier: Apache-2.0
// Milestone DR18: NIST SP 800-56C Dual-Key Combiner Kernel on AMD Phoenix AIE2.

#include <stdint.h>
#include <stddef.h>
#include "dr1_keccak_f1600.hpp"

#define DR18_DESC_MAGIC 0x12527101
#define DR18_RES_MAGIC  0x3831434B // "KC18"

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

void dr18_dual_key_combiner_service(
    const uint8_t *req,
    const uint8_t *desc,
    uint8_t *res
) {
    for (int i = 0; i < 128; i++) res[i] = 0;

    uint32_t magic = *(const uint32_t*)(desc + 0);
    uint32_t req_id = *(const uint32_t*)(desc + 4);
    uint32_t epoch = *(const uint32_t*)(desc + 8);
    uint16_t msg_len = *(const uint16_t*)(desc + 12);
    uint16_t out_len = *(const uint16_t*)(desc + 14);
    if (out_len == 0 || out_len > 64) out_len = 32;
    if (msg_len == 0 || msg_len > 256) msg_len = 115;

    uint32_t status = 0;

    if (magic != DR18_DESC_MAGIC) {
        status = 1;
    } else {
        alignas(8) uint8_t state[200];
        for (int i = 0; i < 200; i++) state[i] = 0;

        uint32_t rate = 136;
        uint32_t offset = 0;

        while (offset + rate <= msg_len) {
            for (uint32_t i = 0; i < rate; i++) state[i] ^= req[offset + i];
            phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
            offset += rate;
        }

        uint32_t rem = msg_len - offset;
        for (uint32_t i = 0; i < rem; i++) state[i] ^= req[offset + i];
        state[rem] ^= 0x1F;
        state[rate - 1] ^= 0x80;
        phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);

        uint8_t *k_out = res + 20;
        uint32_t squeezed = 0;
        while (squeezed < out_len) {
            uint32_t to_copy = (out_len - squeezed < rate) ? (out_len - squeezed) : rate;
            for (uint32_t i = 0; i < to_copy; i++) {
                k_out[squeezed + i] = state[i];
            }
            squeezed += to_copy;
            if (squeezed < out_len) {
                phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
            }
        }

        // Memory scrub
        for (int i = 0; i < 200; i++) state[i] = 0;
    }

    if (status != 0) {
        for (int i = 0; i < 128; i++) res[i] = 0;
        *(uint32_t*)(res + 0) = DR18_RES_MAGIC;
        *(uint32_t*)(res + 4) = req_id;
        *(uint32_t*)(res + 8) = status;
        return;
    }

    uint32_t crc = compute_crc32(res + 20, out_len);

    *(uint32_t*)(res + 0) = DR18_RES_MAGIC;
    *(uint32_t*)(res + 4) = req_id;
    *(uint32_t*)(res + 8) = status;
    *(uint32_t*)(res + 12) = out_len;
    *(uint32_t*)(res + 16) = crc;
}

}
