// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine
 * Memory partitioning models and distributed polynomial arithmetic for AMD Phoenix AIE2 (XDNA1).
 */
#ifndef DR29_CNSA_DISTRIBUTED_INTERNAL_HPP
#define DR29_CNSA_DISTRIBUTED_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR29_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr29 {

static const uint32_t Q_MLDSA = 8380417; // ML-DSA modulus
static const uint32_t Q_MLKEM = 3329;    // ML-KEM modulus

struct TilePartitionInfo {
    uint32_t algo_type;
    uint32_t tile_index;
    uint32_t start_row;
    uint32_t num_rows;
    uint32_t row_length; // l
    uint32_t polys_on_tile;
    uint32_t matrix_bytes;
    uint32_t vector_bytes;
    uint32_t total_sram_kb;
    uint32_t is_under_44kb_bound;
};

__attribute__((noinline))
static TilePartitionInfo compute_partition_info(uint32_t algo_type, uint32_t tile_index, uint32_t num_tiles) {
    TilePartitionInfo info;
    info.algo_type = algo_type;
    info.tile_index = tile_index;

    if (algo_type == 1) {
        // ML-DSA-87: k=8, l=7, 56 polys total, 4 tiles -> 2 rows per tile
        uint32_t k = 8;
        uint32_t l = 7;
        uint32_t rows_per_tile = k / num_tiles;
        info.start_row = tile_index * rows_per_tile;
        info.num_rows = rows_per_tile;
        info.row_length = l;
        info.polys_on_tile = rows_per_tile * l; // 2 * 7 = 14 polys
        info.matrix_bytes = info.polys_on_tile * 256 * 4; // 14 * 1024 = 14336 B (32-bit words)
        info.vector_bytes = l * 256 * 4; // 7 * 1024 = 7168 B
        uint32_t total_bytes = info.matrix_bytes + info.vector_bytes + (rows_per_tile * 256 * 4); // + accum
        info.total_sram_kb = (total_bytes + 1023) / 1024; // 23 KB
        info.is_under_44kb_bound = (info.total_sram_kb <= 44) ? 1 : 0;
    } else {
        // ML-KEM-1024: k=4, l=4, 16 polys total, 4 tiles -> 1 row per tile
        uint32_t k = 4;
        uint32_t l = 4;
        uint32_t rows_per_tile = k / num_tiles;
        info.start_row = tile_index * rows_per_tile;
        info.num_rows = rows_per_tile;
        info.row_length = l;
        info.polys_on_tile = rows_per_tile * l; // 1 * 4 = 4 polys
        info.matrix_bytes = info.polys_on_tile * 256 * 2; // 4 * 512 = 2048 B (16-bit words)
        info.vector_bytes = l * 256 * 2; // 4 * 512 = 2048 B
        uint32_t total_bytes = info.matrix_bytes + info.vector_bytes + (rows_per_tile * 256 * 2); // + accum
        info.total_sram_kb = (total_bytes + 1023) / 1024; // 5 KB
        info.is_under_44kb_bound = (info.total_sram_kb <= 44) ? 1 : 0;
    }
    return info;
}

// Compute tile-resident matrix row dot-product with vector:
// out_rows[r][j] = sum_{c=0}^{l-1} (matrix_rows[r][c][j] * vector_s[c][j]) mod q
__attribute__((noinline))
static void compute_mldsa_row_accum(
    const uint32_t* matrix_rows, // [num_rows][l][256]
    const uint32_t* vector_s,   // [l][256]
    uint32_t* out_rows,         // [num_rows][256]
    uint32_t num_rows,
    uint32_t l
) {
    DR29_DISABLE_UNROLL
    for (uint32_t r = 0; r < num_rows; ++r) {
        // Zero accumulator for this row
        for (int j = 0; j < 256; ++j) {
            out_rows[r * 256 + j] = 0;
        }

        for (uint32_t c = 0; c < l; ++c) {
            const uint32_t* a_poly = matrix_rows + (r * l + c) * 256;
            const uint32_t* s_poly = vector_s + c * 256;
            uint32_t* acc_poly = out_rows + r * 256;

            DR29_DISABLE_UNROLL
            for (int j = 0; j < 256; ++j) {
                uint64_t prod = (uint64_t)a_poly[j] * (uint64_t)s_poly[j];
                uint64_t sum = (uint64_t)acc_poly[j] + (prod % Q_MLDSA);
                acc_poly[j] = (uint32_t)(sum % Q_MLDSA);
            }
        }
    }
}

__attribute__((noinline))
static void compute_mlkem_row_accum(
    const uint16_t* matrix_rows, // [num_rows][l][256]
    const uint16_t* vector_s,   // [l][256]
    uint16_t* out_rows,         // [num_rows][256]
    uint32_t num_rows,
    uint32_t l
) {
    DR29_DISABLE_UNROLL
    for (uint32_t r = 0; r < num_rows; ++r) {
        for (int j = 0; j < 256; ++j) {
            out_rows[r * 256 + j] = 0;
        }

        for (uint32_t c = 0; c < l; ++c) {
            const uint16_t* a_poly = matrix_rows + (r * l + c) * 256;
            const uint16_t* s_poly = vector_s + c * 256;
            uint16_t* acc_poly = out_rows + r * 256;

            DR29_DISABLE_UNROLL
            for (int j = 0; j < 256; ++j) {
                uint32_t prod = (uint32_t)a_poly[j] * (uint32_t)s_poly[j];
                uint32_t sum = (uint32_t)acc_poly[j] + (prod % Q_MLKEM);
                acc_poly[j] = (uint16_t)(sum % Q_MLKEM);
            }
        }
    }
}

} // namespace dr29

#endif // DR29_CNSA_DISTRIBUTED_INTERNAL_HPP
