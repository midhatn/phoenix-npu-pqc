
#include <stdint.h>

namespace {

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

// Precomputed powers of omega = 3061 mod 3329 (128 twiddles)
static const int16_t W[128] = {
    1, 3061, 1915, 2775, 1996, 1041, 648, 2773, 2532, 540, 1756, 2110, 450, 2573, 2868, 375, 2699, 2390, 1977, 2804, 882, 3312, 1227, 735, 2760, 2687, 2277, 2300, 2794, 233, 807, 109, 749, 2337, 2865, 1179, 283, 723, 2647, 3010, 2267, 1651, 289, 2444, 821, 3015, 927, 1239, 848, 2437, 2697, 2926, 1476, 583, 219, 1230, 3260, 1847, 1025, 1607, 2094, 1409, 1894, 1745, 1729, 2688, 2009, 886, 2240, 2229, 1848, 757, 193, 1540, 76, 2935, 2393, 1173, 1891, 2549, 2642, 1021, 2679, 1092, 296, 568, 910, 2466, 1583, 1868, 2055, 1874, 447, 48, 452, 2037, 40, 2596, 33, 1143, 3273, 1692, 2617, 1063, 1410, 1626, 331, 1175, 1355, 3050, 1534, 1684, 1432, 2388, 2513, 2303, 1990, 2649, 2474, 2768, 543, 952, 1197, 2117, 1903, 2662, 2319, 1031
};

// Precomputed 8-bit bit-reversal permutation (256 elements)
static const uint8_t BIT_REV_256[256] = {
    0, 128, 64, 192, 32, 160, 96, 224, 16, 144, 80, 208, 48, 176, 112, 240, 8, 136, 72, 200, 40, 168, 104, 232, 24, 152, 88, 216, 56, 184, 120, 248, 4, 132, 68, 196, 36, 164, 100, 228, 20, 148, 84, 212, 52, 180, 116, 244, 12, 140, 76, 204, 44, 172, 108, 236, 28, 156, 92, 220, 60, 188, 124, 252, 2, 130, 66, 194, 34, 162, 98, 226, 18, 146, 82, 210, 50, 178, 114, 242, 10, 138, 74, 202, 42, 170, 106, 234, 26, 154, 90, 218, 58, 186, 122, 250, 6, 134, 70, 198, 38, 166, 102, 230, 22, 150, 86, 214, 54, 182, 118, 246, 14, 142, 78, 206, 46, 174, 110, 238, 30, 158, 94, 222, 62, 190, 126, 254, 1, 129, 65, 193, 33, 161, 97, 225, 17, 145, 81, 209, 49, 177, 113, 241, 9, 137, 73, 201, 41, 169, 105, 233, 25, 153, 89, 217, 57, 185, 121, 249, 5, 133, 69, 197, 37, 165, 101, 229, 21, 149, 85, 213, 53, 181, 117, 245, 13, 141, 77, 205, 45, 173, 109, 237, 29, 157, 93, 221, 61, 189, 125, 253, 3, 131, 67, 195, 35, 163, 99, 227, 19, 147, 83, 211, 51, 179, 115, 243, 11, 139, 75, 203, 43, 171, 107, 235, 27, 155, 91, 219, 59, 187, 123, 251, 7, 135, 71, 199, 39, 167, 103, 231, 23, 151, 87, 215, 55, 183, 119, 247, 15, 143, 79, 207, 47, 175, 111, 239, 31, 159, 95, 223, 63, 191, 127, 255
};

inline int16_t mod_add_scalar(int16_t a, int16_t b) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}

inline int16_t mod_sub_scalar(int16_t a, int16_t b) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += MOD_Q;
    return static_cast<int16_t>(res);
}

inline int16_t barrett_reduce_scalar(int32_t a) {
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * MOD_Q;
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}

inline void ntt_256_frame(const int16_t* in_frame, int16_t* out_frame) {
    int16_t a[256];

    // 1. Bit-reversal permutation
    #pragma clang loop unroll_count(8)
    for (int i = 0; i < 256; ++i) {
        a[i] = in_frame[BIT_REV_256[i]];
    }

    // 2. Cooley-Tukey 8 Stages (2^1 to 2^8)
    // Stage 1 (m=2, half_m=1, step=128)
    for (int k = 0; k < 256; k += 2) {
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add_scalar(u, v);
        a[k + 1] = mod_sub_scalar(u, v);
    }

    // Stages 2..8
    for (int stage = 2; stage <= 8; ++stage) {
        int m = 1 << stage;
        int half_m = m >> 1;
        int step = 256 >> stage;

        for (int k = 0; k < 256; k += m) {
            for (int j = 0; j < half_m; ++j) {
                int16_t u = a[k + j];
                int16_t w = W[j * step];
                int16_t v_w = (j == 0) ? a[k + j + half_m] : barrett_reduce_scalar(static_cast<int32_t>(a[k + j + half_m]) * w);
                a[k + j] = mod_add_scalar(u, v_w);
                a[k + j + half_m] = mod_sub_scalar(u, v_w);
            }
        }
    }

    // Copy to output
    #pragma clang loop unroll_count(8)
    for (int i = 0; i < 256; ++i) {
        out_frame[i] = a[i];
    }
}

} // anonymous namespace

extern "C" {

void ntt256_kernel(
    const uint32_t* in_packed,
    uint32_t* out_packed
) {
    const int16_t* in_ptr = reinterpret_cast<const int16_t*>(in_packed);
    int16_t* out_ptr = reinterpret_cast<int16_t*>(out_packed);

    // Process 4 parallel 256-point NTT frames (1024 total elements)
    for (int frame = 0; frame < 4; ++frame) {
        ntt_256_frame(in_ptr + frame * 256, out_ptr + frame * 256);
    }
}

}
