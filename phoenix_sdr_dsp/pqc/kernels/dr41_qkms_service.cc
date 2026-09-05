// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR41: Quantum Key Management System (Q-KMS) Integration & Key Lifecycle Engine
 * AMD Phoenix NPU (AIE2 / XDNA1 Architecture) Service Kernel.
 * Dispatched on AIE2 vector compute tiles.
 */

#include <stdint.h>
#include <stddef.h>
#include "dr41_qkms_internal.hpp"

extern "C" {

void dr41_qkms_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack 64-byte descriptor header
    uint32_t magic         = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_code       = *(const uint32_t*)(descriptor_in + 4);
    uint32_t slot_id       = *(const uint32_t*)(descriptor_in + 8);
    uint32_t target_state  = *(const uint32_t*)(descriptor_in + 12);
    uint32_t param_0       = *(const uint32_t*)(descriptor_in + 16);
    uint32_t param_1       = *(const uint32_t*)(descriptor_in + 20);
    uint32_t key_type      = *(const uint32_t*)(descriptor_in + 24);
    uint32_t epoch         = *(const uint32_t*)(descriptor_in + 28);
    uint32_t seq_id        = *(const uint32_t*)(descriptor_in + 32);

    // Zero out full 2048-byte result buffer using 32-bit scalar writes
    uint32_t* res_u32 = (uint32_t*)result_out;
    DR41_DISABLE_UNROLL
    _Pragma("clang loop vectorize(disable)")
    for (size_t i = 0; i < 512; ++i) {
        res_u32[i] = 0;
    }

    // 2. Validate magic header
    if (magic != dr41::MAGIC_HEADER) {
        *(uint32_t*)(result_out + 0)  = dr41::STATUS_ERR_INVALID_MAGIC;
        *(uint32_t*)(result_out + 4)  = op_code;
        *(uint32_t*)(result_out + 8)  = slot_id;
        *(uint32_t*)(result_out + 12) = dr41::STATE_EMPTY;
        *(uint32_t*)(result_out + 16) = 0;
        return;
    }

    // 3. Validate slot_id bounds
    if (op_code != dr41::OP_VAULT_ZEROIZE || slot_id != 0xFF) {
        if (slot_id >= dr41::NUM_VAULT_SLOTS) {
            *(uint32_t*)(result_out + 0)  = dr41::STATUS_ERR_INVALID_SLOT;
            *(uint32_t*)(result_out + 4)  = op_code;
            *(uint32_t*)(result_out + 8)  = slot_id;
            *(uint32_t*)(result_out + 12) = dr41::STATE_EMPTY;
            *(uint32_t*)(result_out + 16) = 0;
            return;
        }
    }

    // 4. Ingress Vault Bank from request buffer (offset 128..639)
    dr41::TileVaultSlot vault[dr41::NUM_VAULT_SLOTS];
    const uint8_t* bank_src = request_in + 128;
    DR41_DISABLE_UNROLL
    _Pragma("clang loop vectorize(disable)")
    for (size_t i = 0; i < dr41::NUM_VAULT_SLOTS; ++i) {
        const uint8_t* s_ptr = bank_src + i * 64;
        vault[i].state    = *(const uint32_t*)(s_ptr + 0);
        vault[i].key_type = *(const uint32_t*)(s_ptr + 4);
        dr41::copy16_bytes(vault[i].key_id, s_ptr + 8);
        dr41::copy32_bytes(vault[i].key_material, s_ptr + 24);
        vault[i].epoch = *(const uint32_t*)(s_ptr + 56);
    }

    uint32_t status = dr41::STATUS_SUCCESS;
    uint32_t current_state = dr41::STATE_EMPTY;
    uint32_t checksum = 0;

    // 5. Execute Q-KMS Lifecycle Operation
    if (op_code == dr41::OP_VAULT_STORE) {
        const uint8_t* raw_key = request_in;
        const uint8_t* raw_id  = request_in + 32;

        vault[slot_id].state = (target_state == dr41::STATE_PRE_ACTIVE || target_state == dr41::STATE_ACTIVE)
                               ? target_state : dr41::STATE_ACTIVE;
        vault[slot_id].key_type = key_type;
        vault[slot_id].epoch    = epoch;

        dr41::copy16_bytes(vault[slot_id].key_id, raw_id);
        dr41::copy16_bytes(result_out + 64, raw_id);

        dr41::copy32_bytes(vault[slot_id].key_material, raw_key);
        dr41::copy32_bytes(result_out + 32, raw_key);

        current_state = vault[slot_id].state;
        checksum = dr41::compute_slot_checksum(&vault[slot_id]);

    } else if (op_code == dr41::OP_VAULT_DERIVE) {
        uint32_t s0 = param_0;
        uint32_t s1 = param_1;
        if (s0 >= dr41::NUM_VAULT_SLOTS || s1 >= dr41::NUM_VAULT_SLOTS) {
            *(uint32_t*)(result_out + 0)  = dr41::STATUS_ERR_INVALID_SLOT;
            *(uint32_t*)(result_out + 4)  = op_code;
            *(uint32_t*)(result_out + 8)  = slot_id;
            *(uint32_t*)(result_out + 12) = dr41::STATE_EMPTY;
            *(uint32_t*)(result_out + 16) = 0;
            return;
        }

        if (vault[s0].state == dr41::STATE_COMPROMISED || vault[s1].state == dr41::STATE_COMPROMISED) {
            *(uint32_t*)(result_out + 0)  = dr41::STATUS_ERR_KEY_COMPROMISED;
            *(uint32_t*)(result_out + 4)  = op_code;
            *(uint32_t*)(result_out + 8)  = slot_id;
            *(uint32_t*)(result_out + 12) = dr41::STATE_COMPROMISED;
            *(uint32_t*)(result_out + 16) = 0;
            return;
        }

        if (vault[s0].state != dr41::STATE_ACTIVE || vault[s1].state != dr41::STATE_ACTIVE) {
            *(uint32_t*)(result_out + 0)  = dr41::STATUS_ERR_SLOT_EXPIRED;
            *(uint32_t*)(result_out + 4)  = op_code;
            *(uint32_t*)(result_out + 8)  = slot_id;
            *(uint32_t*)(result_out + 12) = vault[s0].state;
            *(uint32_t*)(result_out + 16) = 0;
            return;
        }

        const uint8_t* context_salt = request_in;
        uint8_t derived_key[32];
        dr41::sp800_56c_dual_kdf(vault[s0].key_material, vault[s1].key_material, context_salt, derived_key);

        // Derive Key ID: SHA256(derived_key || "ID")[:16]
        dr41::Sha256Ctx ctx;
        uint8_t id_hash[32];
        dr41::sha256_init(&ctx);
        dr41::sha256_update(&ctx, derived_key, 32);
        dr41::sha256_update(&ctx, (const uint8_t*)"ID", 2);
        dr41::sha256_final(&ctx, id_hash);

        vault[slot_id].state    = dr41::STATE_ACTIVE;
        vault[slot_id].key_type = dr41::KEY_TYPE_DERIVED_SESSION;
        vault[slot_id].epoch    = epoch;

        dr41::copy16_bytes(vault[slot_id].key_id, id_hash);
        dr41::copy16_bytes(result_out + 64, id_hash);

        dr41::copy32_bytes(vault[slot_id].key_material, derived_key);
        dr41::copy32_bytes(result_out + 32, derived_key);

        current_state = dr41::STATE_ACTIVE;
        checksum = dr41::compute_slot_checksum(&vault[slot_id]);

    } else if (op_code == dr41::OP_VAULT_TRANSITION) {
        uint32_t cur_state = vault[slot_id].state;
        if (!dr41::is_valid_transition(cur_state, target_state)) {
            *(uint32_t*)(result_out + 0)  = dr41::STATUS_ERR_ILLEGAL_TRANSITION;
            *(uint32_t*)(result_out + 4)  = op_code;
            *(uint32_t*)(result_out + 8)  = slot_id;
            *(uint32_t*)(result_out + 12) = cur_state;
            *(uint32_t*)(result_out + 16) = dr41::compute_slot_checksum(&vault[slot_id]);
            return;
        }

        vault[slot_id].state = target_state;
        if (target_state == dr41::STATE_DESTROYED) {
            uint32_t* id32 = (uint32_t*)vault[slot_id].key_id;
            uint32_t* mat32 = (uint32_t*)vault[slot_id].key_material;
            DR41_DISABLE_UNROLL
            for (size_t b = 0; b < 4; ++b) id32[b] = 0;
            DR41_DISABLE_UNROLL
            for (size_t b = 0; b < 8; ++b) mat32[b] = 0;
        }

        current_state = target_state;
        checksum = dr41::compute_slot_checksum(&vault[slot_id]);

        dr41::copy32_bytes(result_out + 32, vault[slot_id].key_material);
        dr41::copy16_bytes(result_out + 64, vault[slot_id].key_id);

    } else if (op_code == dr41::OP_VAULT_ZEROIZE) {
        if (slot_id == 0xFF) {
            DR41_DISABLE_UNROLL
            for (size_t i = 0; i < dr41::NUM_VAULT_SLOTS; ++i) {
                vault[i].state = dr41::STATE_DESTROYED;
                uint32_t* id32 = (uint32_t*)vault[i].key_id;
                uint32_t* mat32 = (uint32_t*)vault[i].key_material;
                DR41_DISABLE_UNROLL
                for (size_t b = 0; b < 4; ++b) id32[b] = 0;
                DR41_DISABLE_UNROLL
                for (size_t b = 0; b < 8; ++b) mat32[b] = 0;
            }
        } else {
            vault[slot_id].state = dr41::STATE_DESTROYED;
            uint32_t* id32 = (uint32_t*)vault[slot_id].key_id;
            uint32_t* mat32 = (uint32_t*)vault[slot_id].key_material;
            DR41_DISABLE_UNROLL
            for (size_t b = 0; b < 4; ++b) id32[b] = 0;
            DR41_DISABLE_UNROLL
            for (size_t b = 0; b < 8; ++b) mat32[b] = 0;
        }

        current_state = dr41::STATE_DESTROYED;
        checksum = 0;

    } else if (op_code == dr41::OP_VAULT_QUERY) {
        current_state = vault[slot_id].state;
        checksum = dr41::compute_slot_checksum(&vault[slot_id]);

        dr41::copy32_bytes(result_out + 32, vault[slot_id].key_material);
        dr41::copy16_bytes(result_out + 64, vault[slot_id].key_id);

        *(uint32_t*)(result_out + 80) = vault[slot_id].state;
        *(uint32_t*)(result_out + 84) = vault[slot_id].key_type;
        *(uint32_t*)(result_out + 88) = vault[slot_id].epoch;

    } else {
        status = dr41::STATUS_ERR_UNSUPPORTED_OP;
        current_state = dr41::STATE_EMPTY;
        checksum = 0;
    }

    // 6. Finalize result header (32 bytes)
    *(uint32_t*)(result_out + 0)  = status;
    *(uint32_t*)(result_out + 4)  = op_code;
    *(uint32_t*)(result_out + 8)  = slot_id;
    *(uint32_t*)(result_out + 12) = current_state;
    *(uint32_t*)(result_out + 16) = checksum;
}

} // extern "C"
