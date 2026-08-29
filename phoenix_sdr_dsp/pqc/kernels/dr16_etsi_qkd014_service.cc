// SPDX-License-Identifier: Apache-2.0
// Milestone DR16: ETSI GS QKD 014 Key Ingress Kernel on AMD Phoenix AIE2 (Peano LLVM C++).

#include <stdint.h>
#include <stddef.h>

#define DR16_DESC_MAGIC 0x10527101
#define DR16_RES_MAGIC  0x36314B51 // "QK16"

static uint32_t g_last_epoch = 0;
static uint32_t g_active_slot = 0;
static uint8_t  g_sealed_qkd_ring[4][64];

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

void dr16_etsi_qkd014_ingress_service(
    const uint8_t *req,
    const uint8_t *desc,
    uint8_t *res
) {
    for (int i = 0; i < 64; i++) res[i] = 0;

    uint32_t magic = *(const uint32_t*)(desc + 0);
    uint32_t req_id = *(const uint32_t*)(desc + 4);
    uint32_t epoch = *(const uint32_t*)(desc + 8);
    uint16_t key_len = *(const uint16_t*)(desc + 12);
    const uint8_t *key_uuid = desc + 16;

    uint32_t status = 0;

    if (magic != DR16_DESC_MAGIC) {
        status = 1; // STATUS_INVALID_MAGIC
    } else if (epoch <= g_last_epoch && g_last_epoch != 0) {
        status = 3; // STATUS_STALE_EPOCH
    } else {
        uint32_t slot = g_active_slot % 4;
        for (int i = 0; i < 64; i++) {
            g_sealed_qkd_ring[slot][i] = req[i];
        }
        g_last_epoch = epoch;
        g_active_slot++;
    }

    if (status != 0) {
        // Fail-closed zeroization
        for (int i = 0; i < 64; i++) res[i] = 0;
        *(uint32_t*)(res + 0) = DR16_RES_MAGIC;
        *(uint32_t*)(res + 4) = req_id;
        *(uint32_t*)(res + 8) = status;
        return;
    }

    uint32_t crc = compute_crc32(req, 64);

    *(uint32_t*)(res + 0) = DR16_RES_MAGIC;
    *(uint32_t*)(res + 4) = req_id;
    *(uint32_t*)(res + 8) = status;
    *(uint32_t*)(res + 12) = (g_active_slot % 4);
    *(uint32_t*)(res + 16) = crc;

    for (int i = 0; i < 16; i++) {
        res[20 + i] = key_uuid[i];
    }
}

}
