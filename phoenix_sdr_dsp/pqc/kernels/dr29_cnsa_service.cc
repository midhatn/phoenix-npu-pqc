// SPDX-License-Identifier: Apache-2.0
// Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine Kernel.
// Target: AMD Phoenix NPU (AIE2 / XDNA1 4-Tile Cluster & MemTile Pipeline).
// DOI: 10.5281/zenodo.22164124

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define DR29_DESC_MAGIC 0x4E432901 // "\x01)CN"
#define DR29_RES_MAGIC  0x39324E43 // "CN29"
#define N_DEGREE 256

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

// Barrett reduction for ML-DSA mod 8380417
static inline int32_t barrett_reduce_8380417(int64_t a) {
    int64_t v = (a * 512) >> 32;
    int32_t r = (int32_t)(a - v * 8380417);
    while (r >= 8380417) r -= 8380417;
    while (r < 0) r += 8380417;
    return r;
}

extern "C" {

void dr29_submatrix_vector_product_service(
    const int32_t *submatrix_polys, // [num_rows][num_cols][256]
    uint32_t num_rows,
    uint32_t num_cols,
    const int32_t *subvector,       // [num_cols][256]
    int32_t *out_partial_accum,     // [num_rows][256]
    uint8_t *out_header
) {
    for (uint32_t r = 0; r < num_rows; r++) {
        for (int i = 0; i < N_DEGREE; i++) {
            out_partial_accum[r * N_DEGREE + i] = 0;
        }
        for (uint32_t c = 0; c < num_cols; c++) {
            const int32_t *poly_A = submatrix_polys + (r * num_cols + c) * N_DEGREE;
            const int32_t *poly_s = subvector + c * N_DEGREE;

            for (int i = 0; i < N_DEGREE; i++) {
                int32_t a_coeff = poly_A[i];
                if (a_coeff == 0) continue;
                for (int j = 0; j < N_DEGREE; j++) {
                    int64_t prod = (int64_t)a_coeff * poly_s[j];
                    int k = i + j;
                    if (k < N_DEGREE) {
                        out_partial_accum[r * N_DEGREE + k] = barrett_reduce_8380417(out_partial_accum[r * N_DEGREE + k] + prod);
                    } else {
                        out_partial_accum[r * N_DEGREE + (k - N_DEGREE)] = barrett_reduce_8380417(out_partial_accum[r * N_DEGREE + (k - N_DEGREE)] - prod);
                    }
                }
            }
        }
    }

    uint32_t crc = compute_crc32((const uint8_t*)out_partial_accum, num_rows * N_DEGREE * sizeof(int32_t));
    *(uint32_t*)(out_header + 0) = DR29_RES_MAGIC;
    *(uint32_t*)(out_header + 4) = 0; // Status: 0 = PASS
    *(uint32_t*)(out_header + 8) = crc;
}

}
