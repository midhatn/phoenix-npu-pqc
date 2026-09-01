// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR26: AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling
 * Architecture geometry definitions and spatial topology partitioning algorithms.
 */
#ifndef DR26_MULTI_ARCH_INTERNAL_HPP
#define DR26_MULTI_ARCH_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR26_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr26 {

struct ArchGeometry {
    uint32_t rows;
    uint32_t cols;
    uint32_t total_tiles;
    uint32_t dma_channels_per_col;
    uint32_t sram_per_tile_kb;
    uint32_t prog_mem_per_tile_kb;
    uint32_t peak_tops;
};

__attribute__((noinline))
static ArchGeometry get_arch_geometry(uint32_t arch_id) {
    ArchGeometry geom;
    if (arch_id == 0) {
        // Phoenix (XDNA 1)
        geom.rows = 4;
        geom.cols = 5;
        geom.total_tiles = 20;
        geom.dma_channels_per_col = 2;
        geom.sram_per_tile_kb = 64;
        geom.prog_mem_per_tile_kb = 16;
        geom.peak_tops = 10;
    } else if (arch_id == 1) {
        // Strix Point (XDNA 2)
        geom.rows = 4;
        geom.cols = 8;
        geom.total_tiles = 32;
        geom.dma_channels_per_col = 4;
        geom.sram_per_tile_kb = 64;
        geom.prog_mem_per_tile_kb = 16;
        geom.peak_tops = 50;
    } else {
        // Alveo V70 (Datacenter)
        geom.rows = 8;
        geom.cols = 38;
        geom.total_tiles = 304;
        geom.dma_channels_per_col = 4;
        geom.sram_per_tile_kb = 64;
        geom.prog_mem_per_tile_kb = 16;
        geom.peak_tops = 200;
    }
    return geom;
}

// Validates spatial fit of requested tiles on target architecture
__attribute__((noinline))
static void validate_spatial_fit(
    uint32_t arch_id,
    uint32_t req_tiles,
    uint32_t* out_is_valid,
    uint32_t* out_max_concurrent
) {
    ArchGeometry geom = get_arch_geometry(arch_id);
    if (req_tiles == 0 || req_tiles > geom.total_tiles) {
        *out_is_valid = 0; // Fit failure
        *out_max_concurrent = 0;
    } else {
        *out_is_valid = 1; // Valid fit
        *out_max_concurrent = geom.total_tiles / req_tiles;
    }
}

// Partitions column allocation across concurrent PQC execution pipelines
__attribute__((noinline))
static void partition_columns(
    uint32_t arch_id,
    uint32_t requested_instances,
    uint32_t* out_partitions, // [start_col, num_cols] pairs
    uint32_t* out_actual_instances
) {
    ArchGeometry geom = get_arch_geometry(arch_id);
    uint32_t instances = (requested_instances == 0) ? 1 : requested_instances;
    if (instances > geom.cols) instances = geom.cols;

    uint32_t cols_per_instance = geom.cols / instances;
    uint32_t remainder = geom.cols % instances;

    uint32_t cur_col = 0;
    DR26_DISABLE_UNROLL
    for (uint32_t i = 0; i < instances; ++i) {
        uint32_t num = cols_per_instance + (i < remainder ? 1 : 0);
        out_partitions[2 * i] = cur_col;
        out_partitions[2 * i + 1] = num;
        cur_col += num;
    }
    *out_actual_instances = instances;
}

} // namespace dr26

#endif // DR26_MULTI_ARCH_INTERNAL_HPP
