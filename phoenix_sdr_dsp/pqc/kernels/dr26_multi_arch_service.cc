// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR26: AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling AIE2 Kernel.
 * Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
 */

#include <stdint.h>
#include <stddef.h>
#include "dr26_multi_arch_internal.hpp"

extern "C" {

void dr26_multi_arch_service(
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
    uint32_t target_arch = *(const uint32_t*)(descriptor_in + 8);
    uint32_t req_tiles = *(const uint32_t*)(descriptor_in + 12);
    uint32_t epoch = *(const uint32_t*)(descriptor_in + 16);

    // Check magic
    if (magic != 0x01264152) {
        *(uint32_t*)(result_out + 0) = 0xDEAD0003;
        *(uint32_t*)(result_out + 4) = 0;
        *(uint32_t*)(result_out + 8) = 1; // Error invalid magic
        return;
    }

    // Zero out result header
    for (int i = 0; i < 16; ++i) result_out[i] = 0;
    *(uint32_t*)(result_out + 0) = 0x01264152;
    *(uint32_t*)(result_out + 4) = epoch;

    if (op_mode == 0) {
        // MODE_QUERY_ARCH_TOPOLOGY
        dr26::ArchGeometry geom = dr26::get_arch_geometry(target_arch);
        uint32_t* res_data = (uint32_t*)(result_out + 16);
        res_data[0] = geom.rows;
        res_data[1] = geom.cols;
        res_data[2] = geom.total_tiles;
        res_data[3] = geom.dma_channels_per_col;
        res_data[4] = geom.sram_per_tile_kb;
        res_data[5] = geom.prog_mem_per_tile_kb;
        res_data[6] = geom.peak_tops;

        *(uint32_t*)(result_out + 8) = 0; // Success
        *(uint32_t*)(result_out + 12) = 28; // 7 uint32 fields = 28 bytes
    } else if (op_mode == 1) {
        // MODE_VALIDATE_GRID_FIT
        uint32_t is_valid = 0;
        uint32_t max_concurrent = 0;
        dr26::validate_spatial_fit(target_arch, req_tiles, &is_valid, &max_concurrent);

        uint32_t* res_data = (uint32_t*)(result_out + 16);
        res_data[0] = is_valid;
        res_data[1] = max_concurrent;

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 8;
    } else if (op_mode == 2) {
        // MODE_PARTITION_COLUMNS
        uint32_t requested_instances = req_tiles;
        uint32_t* res_data = (uint32_t*)(result_out + 16);
        uint32_t* partitions = res_data + 1;
        uint32_t actual_instances = 0;

        dr26::partition_columns(target_arch, requested_instances, partitions, &actual_instances);
        res_data[0] = actual_instances;

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 4 + 8 * actual_instances;
    } else if (op_mode == 3) {
        // MODE_EMIT_MLIR_TOPOLOGY
        dr26::ArchGeometry geom = dr26::get_arch_geometry(target_arch);
        uint32_t* res_data = (uint32_t*)(result_out + 16);
        // Pack binary device topology vector:
        // [magic_target, rows, cols, total_tiles, shim_rows, mem_tiles, dma_streams]
        res_data[0] = 0x4D4C4952; // "MLIR"
        res_data[1] = target_arch;
        res_data[2] = geom.rows;
        res_data[3] = geom.cols;
        res_data[4] = geom.total_tiles;
        res_data[5] = (target_arch == 2) ? 2 : 1; // Shim rows
        res_data[6] = geom.dma_channels_per_col * geom.cols; // Total device DMA streams

        *(uint32_t*)(result_out + 8) = 0;
        *(uint32_t*)(result_out + 12) = 28;
    } else {
        *(uint32_t*)(result_out + 8) = 0xFF; // Unsupported mode
    }
}

} // extern "C"
