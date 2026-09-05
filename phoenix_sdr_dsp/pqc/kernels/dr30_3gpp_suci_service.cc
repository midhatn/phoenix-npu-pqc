// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR30: 3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor AIE2 Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr30_3gpp_suci_internal.hpp"

extern "C" {

void dr30_3gpp_suci_service(
    const uint8_t* restrict request_in,
    const uint8_t* restrict descriptor_in,
    uint8_t* restrict result_out,
    uint32_t request_slots,
    uint32_t descriptor_slots,
    uint32_t result_slots
) {
    // 1. Unpack descriptor
    uint32_t magic = *(const uint32_t*)(descriptor_in + 0);
    uint32_t op_mode = *(const uint32_t*)(descriptor_in + 4);
    uint32_t profile_id = *(const uint32_t*)(descriptor_in + 8);
    uint32_t hn_key_id = *(const uint32_t*)(descriptor_in + 12);
    uint32_t suci_len = *(const uint32_t*)(descriptor_in + 16);
    uint32_t epoch = *(const uint32_t*)(descriptor_in + 20);
    uint32_t routing_ind = *(const uint32_t*)(descriptor_in + 24);
    uint32_t mcc_mnc = *(const uint32_t*)(descriptor_in + 28);

    // Check magic
    if (magic != 0x01305355) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0006;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error: invalid magic
        return;
    }

    // Zero out header
    for (int i = 0; i < 16; ++i) result_out[i] = 0;
    *(uint32_t*)(result_out + 0) = 0x01305355;
    *(uint32_t*)(result_out + 4) = epoch;

    if (op_mode == 0) {
        // MODE_SUCI_PARSE_VALIDATE
        // Validate 3GPP profile: Profile C (3) or Profile D (4)
        uint32_t is_valid = 0;
        if ((profile_id == 3 || profile_id == 4) && hn_key_id > 0 && suci_len >= 32) {
            is_valid = 1;
        }

        uint32_t* res_fields = (uint32_t*)(result_out + 16);
        res_fields[0] = is_valid;
        res_fields[1] = profile_id;
        res_fields[2] = hn_key_id;
        res_fields[3] = routing_ind;
        res_fields[4] = mcc_mnc;
        res_fields[5] = suci_len;

        *(uint32_t*)(result_out + 8) = 0; // Hardware status success
        *(uint32_t*)(result_out + 12) = 24; // 6 uint32s
    }
    else if (op_mode == 1) {
        // MODE_SUCI_DECAPSULATE_DERIVE
        // Ingests: shared_secret (32 bytes at offset 0), ephem_pubkey (32 bytes at offset 32)
        const uint8_t* ss = request_in;
        const uint8_t* ephem = request_in + 32;
        uint8_t k_enc[16];
        uint8_t k_mac[16];

        dr30::derive_suci_keys(ss, ephem, k_enc, k_mac);

        // Copy derived keys to result
        uint8_t* out_data = result_out + 16;
        for (int i = 0; i < 16; ++i) {
            out_data[i] = k_enc[i];
            out_data[16 + i] = k_mac[i];
        }

        dr30::secure_zeroize(k_enc, sizeof(k_enc));
        dr30::secure_zeroize(k_mac, sizeof(k_mac));

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 32;
    }
    else if (op_mode == 2) {
        // MODE_SUCI_DECONCEAL_VERIFY
        // Request format:
        // offset 0: K_enc (16 bytes)
        // offset 16: K_mac (16 bytes)
        // offset 32: received MAC tag (16 bytes)
        // offset 48: encrypted payload (e.g. 16 or 32 bytes MSIN)
        const uint8_t* k_enc = request_in + 0;
        const uint8_t* k_mac = request_in + 16;
        const uint8_t* recv_mac = request_in + 32;
        const uint8_t* enc_payload = request_in + 48;
        size_t payload_len = (suci_len > 48) ? (suci_len - 48) : 16;
        if (payload_len > 64) payload_len = 64;

        uint8_t calc_mac[16];
        dr30::compute_suci_mac(k_mac, enc_payload, payload_len, calc_mac);

        int mac_ok = dr30::ct_compare(recv_mac, calc_mac, 16);

        if (mac_ok) {
            uint8_t* out_plain = result_out + 16;
            dr30::decrypt_supi_payload(k_enc, enc_payload, payload_len, out_plain);
            *(uint32_t*)(result_out + 8) = 0; // Success
            *(uint32_t*)(result_out + 12) = (uint32_t)payload_len;
        } else {
            *(uint32_t*)(result_out + 8) = 0x02; // MAC verification failure
            *(uint32_t*)(result_out + 12) = 0;
        }
    }
    else if (op_mode == 3) {
        // MODE_SUCI_PIPELINE_FULL
        // Complete atomic hardware de-concealment pipeline:
        // offset 0: shared_secret (32 bytes)
        // offset 32: ephem_pubkey (32 bytes)
        // offset 64: received MAC tag (16 bytes)
        // offset 80: encrypted payload (MSIN)
        const uint8_t* ss = request_in + 0;
        const uint8_t* ephem = request_in + 32;
        const uint8_t* recv_mac = request_in + 64;
        const uint8_t* enc_payload = request_in + 80;
        size_t payload_len = (suci_len > 80) ? (suci_len - 80) : 16;
        if (payload_len > 64) payload_len = 64;

        uint8_t k_enc[16];
        uint8_t k_mac[16];
        dr30::derive_suci_keys(ss, ephem, k_enc, k_mac);

        uint8_t calc_mac[16];
        dr30::compute_suci_mac(k_mac, enc_payload, payload_len, calc_mac);

        int mac_ok = dr30::ct_compare(recv_mac, calc_mac, 16);

        if (mac_ok) {
            uint8_t* out_plain = result_out + 16;
            dr30::decrypt_supi_payload(k_enc, enc_payload, payload_len, out_plain);
            *(uint32_t*)(result_out + 8) = 0; // Success
            *(uint32_t*)(result_out + 12) = (uint32_t)payload_len;
        } else {
            *(uint32_t*)(result_out + 8) = 0x02; // MAC failure
            *(uint32_t*)(result_out + 12) = 0;
        }

        // Clean up SRAM secrets
        dr30::secure_zeroize(k_enc, sizeof(k_enc));
        dr30::secure_zeroize(k_mac, sizeof(k_mac));
        dr30::secure_zeroize(calc_mac, sizeof(calc_mac));
    }
    else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported op_mode
    }
}

} // extern "C"
