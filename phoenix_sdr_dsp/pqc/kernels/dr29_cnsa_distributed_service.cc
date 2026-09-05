// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine AIE2 Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr29_cnsa_distributed_internal.hpp"

extern "C" {

void dr29_cnsa_distributed_service(
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
    uint32_t algo_type = *(const uint32_t*)(descriptor_in + 8);
    uint32_t tile_index = *(const uint32_t*)(descriptor_in + 12);
    uint32_t num_tiles = *(const uint32_t*)(descriptor_in + 16);
    uint32_t epoch = *(const uint32_t*)(descriptor_in + 20);

    // Check magic
    if (magic != 0x01294D54) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0005;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error invalid magic
        return;
    }

    // Zero out result header
    for (int i = 0; i < 16; ++i) result_out[i] = 0;
    *(uint32_t*)(result_out + 0) = 0x01294D54;
    *(uint32_t*)(result_out + 4) = epoch;

    if (op_mode == 0) {
        // MODE_DISTRIBUTED_PARTITION
        dr29::TilePartitionInfo info = dr29::compute_partition_info(algo_type, tile_index, num_tiles);
        uint32_t* res_data = (uint32_t*)(result_out + 16);
        res_data[0] = info.algo_type;
        res_data[1] = info.tile_index;
        res_data[2] = info.start_row;
        res_data[3] = info.num_rows;
        res_data[4] = info.row_length;
        res_data[5] = info.polys_on_tile;
        res_data[6] = info.matrix_bytes;
        res_data[7] = info.vector_bytes;
        res_data[8] = info.total_sram_kb;
        res_data[9] = info.is_under_44kb_bound;

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 40; // 10 uint32 fields
    } else if (op_mode == 1) {
        // MODE_DISTRIBUTED_ROW_ACCUM
        if (algo_type == 2) {
            // ML-KEM-1024: 1 row of 4 polys (4 * 512 = 2048 B) + vector s (4 * 512 = 2048 B)
            const uint16_t* matrix_row = (const uint16_t*)request_in;
            const uint16_t* vector_s = (const uint16_t*)(request_in + 2048);
            uint16_t* out_poly = (uint16_t*)(result_out + 16);

            dr29::compute_mlkem_row_accum(matrix_row, vector_s, out_poly, 1, 4);

            *(uint32_t*)(result_out + 8) = 0;
            *(uint32_t*)(result_out + 12) = 512; // 256 * 2 bytes
        } else {
            // ML-DSA-87: 1 row of 7 polys (7 * 1024 = 7168 B) + vector s
            // In request: matrix_row (7 * 256 * 4 B) at offset 0, vector_s packed or computed
            const uint32_t* matrix_row = (const uint32_t*)request_in;
            const uint32_t* vector_s = (const uint32_t*)(request_in + 7168);
            uint32_t* out_poly = (uint32_t*)(result_out + 16);

            dr29::compute_mldsa_row_accum(matrix_row, vector_s, out_poly, 1, 7);

            *(uint32_t*)(result_out + 8) = 0;
            *(uint32_t*)(result_out + 12) = 1024; // 256 * 4 bytes
        }
    } else if (op_mode == 2) {
        // MODE_CLUSTER_AGGREGATE
        // Aggregates 4 polynomials from 4 tiles
        // Input: 4 * 512 bytes (or 4 * 1024 bytes) partial polynomials
        // Computes polynomial norm / sum across cluster
        if (algo_type == 2) {
            // ML-KEM-1024
            const uint16_t* in_polys = (const uint16_t*)request_in;
            uint16_t* out_sum = (uint16_t*)(result_out + 16);
            for (int j = 0; j < 256; ++j) out_sum[j] = 0;

            for (uint32_t t = 0; t < 4; ++t) {
                const uint16_t* p = in_polys + t * 256;
                for (int j = 0; j < 256; ++j) {
                    uint32_t s = (uint32_t)out_sum[j] + (uint32_t)p[j];
                    out_sum[j] = (uint16_t)(s % dr29::Q_MLKEM);
                }
            }
            *(uint32_t*)(result_out + 8) = 0;
            *(uint32_t*)(result_out + 12) = 512;
        } else {
            // ML-DSA-87
            const uint32_t* in_polys = (const uint32_t*)request_in;
            uint32_t* out_sum = (uint32_t*)(result_out + 16);
            for (int j = 0; j < 256; ++j) out_sum[j] = 0;

            for (uint32_t t = 0; t < 4; ++t) {
                const uint32_t* p = in_polys + t * 256;
                for (int j = 0; j < 256; ++j) {
                    uint64_t s = (uint64_t)out_sum[j] + (uint64_t)p[j];
                    out_sum[j] = (uint32_t)(s % dr29::Q_MLDSA);
                }
            }
            *(uint32_t*)(result_out + 8) = 0;
            *(uint32_t*)(result_out + 12) = 1024;
        }
    } else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported mode
    }
}

} // extern "C"
