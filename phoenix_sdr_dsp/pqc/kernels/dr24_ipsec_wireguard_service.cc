// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR24: RFC 9370 Multi-KEM IPsec / WireGuard VPN Co-Processor AIE2 Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr24_ipsec_wireguard_internal.hpp"

extern "C" {

void dr24_ipsec_wireguard_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack 32-byte descriptor
    uint32_t magic = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode = *(const uint32_t*)(descriptor_in + 4);
    uint32_t payload_len = *(const uint32_t*)(descriptor_in + 8);
    uint32_t seq_lo = *(const uint32_t*)(descriptor_in + 12);
    uint32_t seq_hi = *(const uint32_t*)(descriptor_in + 16);
    uint32_t epoch = *(const uint32_t*)(descriptor_in + 20);
    uint32_t kem_mode = *(const uint32_t*)(descriptor_in + 24);

    uint64_t seq_num = ((uint64_t)seq_hi << 32) | (uint64_t)seq_lo;

    // Check magic
    if (magic != 0x01244957) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0001;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error invalid magic
        return;
    }

    // Zero out result header
    for (int i = 0; i < 16; ++i) result_out[i] = 0;
    *(uint32_t*)(result_out + 0) = 0x01244957; // Magic echo
    *(uint32_t*)(result_out + 4) = epoch;

    if (op_mode == 0) {
        // MODE_RFC9370_COMBINE
        // Input: k_classic(32) + k_pqc(32) + k_qkd(32) + ni_nr(64)
        const uint8_t* k_classic = request_in;
        const uint8_t* k_pqc = request_in + 32;
        const uint8_t* k_qkd = request_in + 64;
        const uint8_t* ni_nr = request_in + 96;

        uint8_t* out_ske = result_out + 16;
        uint8_t* out_ska = result_out + 48;
        uint8_t* out_skd = result_out + 80;

        dr24::rfc9370_combine_keys(k_classic, k_pqc, k_qkd, ni_nr, out_ske, out_ska, out_skd);
        *(uint32_t*)(result_out + 8) = 0; // Success
        *(uint32_t*)(result_out + 12) = 96; // Output length
    } else if (op_mode == 1) {
        // MODE_WIREGUARD_ENCAPS
        // Input: ske(32) + ska(32) + plaintext(payload_len)
        const uint8_t* ske = request_in;
        const uint8_t* ska = request_in + 32;
        const uint8_t* pt = request_in + 64;

        uint8_t* out_packet = result_out + 16;
        size_t packet_len = 0;

        dr24::wireguard_encapsulate(ske, ska, seq_num, pt, payload_len, out_packet, &packet_len);
        *(uint32_t*)(result_out + 8) = 0; // Success
        *(uint32_t*)(result_out + 12) = (uint32_t)packet_len;
    } else if (op_mode == 2) {
        // MODE_WIREGUARD_DECAPS
        // Input: ske(32) + ska(32) + packet(payload_len)
        const uint8_t* ske = request_in;
        const uint8_t* ska = request_in + 32;
        const uint8_t* packet = request_in + 64;

        uint64_t out_seq = 0;
        uint8_t* out_pt = result_out + 32;
        size_t out_pt_len = 0;

        int status = dr24::wireguard_decapsulate(ske, ska, packet, payload_len, &out_seq, out_pt, &out_pt_len);
        if (status == 0) {
            *(uint32_t*)(result_out + 8) = 0; // Success
            *(uint32_t*)(result_out + 12) = (uint32_t)out_pt_len;
            *(uint64_t*)(result_out + 16) = out_seq;
            *(uint64_t*)(result_out + 24) = (uint64_t)out_pt_len;
        } else {
            *(uint32_t*)(result_out + 8) = (uint32_t)status; // 1: short, 2: auth fail
            *(uint32_t*)(result_out + 12) = 0;
        }
    } else if (op_mode == 3) {
        // MODE_ASYNC_REKEY
        // Input: skd(32) + rekey_seed(32)
        const uint8_t* skd = request_in;
        const uint8_t* rekey_seed = request_in + 32;

        uint8_t rekey_input[64];
        for (int i = 0; i < 32; ++i) rekey_input[i] = skd[i];
        for (int i = 0; i < 32; ++i) rekey_input[32 + i] = rekey_seed[i];

        uint8_t new_keys[96];
        dr24::shake256_stream(rekey_input, 64, new_keys, 96);

        uint8_t* out_ske = result_out + 16;
        uint8_t* out_ska = result_out + 48;
        uint8_t* out_skd = result_out + 80;

        for (int i = 0; i < 32; ++i) {
            out_ske[i] = new_keys[i];
            out_ska[i] = new_keys[32 + i];
            out_skd[i] = new_keys[64 + i];
        }
        *(uint32_t*)(result_out + 8) = 0; // Success
        *(uint32_t*)(result_out + 12) = 96;
    } else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported mode
    }
}

} // extern "C"
