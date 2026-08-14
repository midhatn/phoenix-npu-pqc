
#include <stdint.h>

namespace {

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;
static constexpr int16_t N_INV = 3316;

static const int16_t W_FWD[128] = {
    1, 3061, 1915, 2775, 1996, 1041, 648, 2773, 2532, 540, 1756, 2110, 450, 2573, 2868, 375, 2699, 2390, 1977, 2804, 882, 3312, 1227, 735, 2760, 2687, 2277, 2300, 2794, 233, 807, 109, 749, 2337, 2865, 1179, 283, 723, 2647, 3010, 2267, 1651, 289, 2444, 821, 3015, 927, 1239, 848, 2437, 2697, 2926, 1476, 583, 219, 1230, 3260, 1847, 1025, 1607, 2094, 1409, 1894, 1745, 1729, 2688, 2009, 886, 2240, 2229, 1848, 757, 193, 1540, 76, 2935, 2393, 1173, 1891, 2549, 2642, 1021, 2679, 1092, 296, 568, 910, 2466, 1583, 1868, 2055, 1874, 447, 48, 452, 2037, 40, 2596, 33, 1143, 3273, 1692, 2617, 1063, 1410, 1626, 331, 1175, 1355, 3050, 1534, 1684, 1432, 2388, 2513, 2303, 1990, 2649, 2474, 2768, 543, 952, 1197, 2117, 1903, 2662, 2319, 1031
};

static const int16_t W_INV[128] = {
    1, 2298, 1010, 667, 1426, 1212, 2132, 2377, 2786, 561, 855, 680, 1339, 1026, 816, 941, 1897, 1645, 1795, 279, 1974, 2154, 2998, 1703, 1919, 2266, 712, 1637, 56, 2186, 3296, 733, 3289, 1292, 2877, 3281, 2882, 1455, 1274, 1461, 1746, 863, 2419, 2761, 3033, 2237, 650, 2308, 687, 780, 1438, 2156, 936, 394, 3253, 1789, 3136, 2572, 1481, 1100, 1089, 2443, 1320, 641, 1600, 1584, 1435, 1920, 1235, 1722, 2304, 1482, 69, 2099, 3110, 2746, 1853, 403, 632, 892, 2481, 2090, 2402, 314, 2508, 885, 3040, 1678, 1062, 319, 682, 2606, 3046, 2150, 464, 992, 2580, 3220, 2522, 3096, 535, 1029, 1052, 642, 569, 2594, 2102, 17, 2447, 525, 1352, 939, 630, 2954, 461, 756, 2879, 1219, 1573, 2789, 797, 556, 2681, 2288, 1333, 554, 1414, 268
};

static const uint8_t BIT_REV[256] = {
    0, 128, 64, 192, 32, 160, 96, 224, 16, 144, 80, 208, 48, 176, 112, 240, 8, 136, 72, 200, 40, 168, 104, 232, 24, 152, 88, 216, 56, 184, 120, 248, 4, 132, 68, 196, 36, 164, 100, 228, 20, 148, 84, 212, 52, 180, 116, 244, 12, 140, 76, 204, 44, 172, 108, 236, 28, 156, 92, 220, 60, 188, 124, 252, 2, 130, 66, 194, 34, 162, 98, 226, 18, 146, 82, 210, 50, 178, 114, 242, 10, 138, 74, 202, 42, 170, 106, 234, 26, 154, 90, 218, 58, 186, 122, 250, 6, 134, 70, 198, 38, 166, 102, 230, 22, 150, 86, 214, 54, 182, 118, 246, 14, 142, 78, 206, 46, 174, 110, 238, 30, 158, 94, 222, 62, 190, 126, 254, 1, 129, 65, 193, 33, 161, 97, 225, 17, 145, 81, 209, 49, 177, 113, 241, 9, 137, 73, 201, 41, 169, 105, 233, 25, 153, 89, 217, 57, 185, 121, 249, 5, 133, 69, 197, 37, 165, 101, 229, 21, 149, 85, 213, 53, 181, 117, 245, 13, 141, 77, 205, 45, 173, 109, 237, 29, 157, 93, 221, 61, 189, 125, 253, 3, 131, 67, 195, 35, 163, 99, 227, 19, 147, 83, 211, 51, 179, 115, 243, 11, 139, 75, 203, 43, 171, 107, 235, 27, 155, 91, 219, 59, 187, 123, 251, 7, 135, 71, 199, 39, 167, 103, 231, 23, 151, 87, 215, 55, 183, 119, 247, 15, 143, 79, 207, 47, 175, 111, 239, 31, 159, 95, 223, 63, 191, 127, 255
};

inline int16_t mod_add(int16_t a, int16_t b) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}

inline int16_t mod_sub(int16_t a, int16_t b) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += MOD_Q;
    return static_cast<int16_t>(res);
}

inline int16_t barrett_reduce(int32_t a) {
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * MOD_Q;
    if (res >= MOD_Q) res -= MOD_Q;
    return static_cast<int16_t>(res);
}

inline void forward_ntt_256(const int16_t* in_poly, int16_t* out_spec) {
    int16_t a[256];
    for (int i = 0; i < 256; ++i) {
        a[i] = in_poly[BIT_REV[i]];
    }

    // Stage 1 (m=2)
    for (int k = 0; k < 256; k += 2) {
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add(u, v);
        a[k + 1] = mod_sub(u, v);
    }

    // Stages 2..8
    for (int stage = 2; stage <= 8; ++stage) {
        int m = 1 << stage;
        int half_m = m >> 1;
        int step = 256 >> stage;

        for (int k = 0; k < 256; k += m) {
            for (int j = 0; j < half_m; ++j) {
                int16_t u = a[k + j];
                int16_t w = W_FWD[j * step];
                int16_t v_w = (j == 0) ? a[k + j + half_m] : barrett_reduce(static_cast<int32_t>(a[k + j + half_m]) * w);
                a[k + j] = mod_add(u, v_w);
                a[k + j + half_m] = mod_sub(u, v_w);
            }
        }
    }

    for (int i = 0; i < 256; ++i) {
        out_spec[i] = a[i];
    }
}

inline void inverse_ntt_256(const int16_t* in_spec, int16_t* out_poly) {
    int16_t a[256];
    for (int i = 0; i < 256; ++i) {
        a[i] = in_spec[BIT_REV[i]];
    }

    // Stage 1 (m=2)
    for (int k = 0; k < 256; k += 2) {
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add(u, v);
        a[k + 1] = mod_sub(u, v);
    }

    // Stages 2..8 with inverse twiddles
    for (int stage = 2; stage <= 8; ++stage) {
        int m = 1 << stage;
        int half_m = m >> 1;
        int step = 256 >> stage;

        for (int k = 0; k < 256; k += m) {
            for (int j = 0; j < half_m; ++j) {
                int16_t u = a[k + j];
                int16_t w = W_INV[j * step];
                int16_t v_w = (j == 0) ? a[k + j + half_m] : barrett_reduce(static_cast<int32_t>(a[k + j + half_m]) * w);
                a[k + j] = mod_add(u, v_w);
                a[k + j + half_m] = mod_sub(u, v_w);
            }
        }
    }

    // Multiply by N^-1 mod q
    for (int i = 0; i < 256; ++i) {
        out_poly[i] = barrett_reduce(static_cast<int32_t>(a[i]) * N_INV);
    }
}

} // anonymous namespace

extern "C" {

void poly_mul_intt_kernel(
    const uint32_t* in_packed_ab,
    uint32_t* out_packed_res
) {
    int16_t a[256];
    int16_t b[256];

    for (int i = 0; i < 256; ++i) {
        uint32_t packed = in_packed_ab[i];
        a[i] = static_cast<int16_t>(packed & 0xFFFF);
        b[i] = static_cast<int16_t>((packed >> 16) & 0xFFFF);
    }

    int16_t A_spec[256];
    int16_t B_spec[256];
    forward_ntt_256(a, A_spec);
    forward_ntt_256(b, B_spec);

    // Pointwise Spectral Multiplication
    int16_t C_spec[256];
    for (int i = 0; i < 256; ++i) {
        C_spec[i] = barrett_reduce(static_cast<int32_t>(A_spec[i]) * static_cast<int32_t>(B_spec[i]));
    }

    int16_t c_poly[256];
    int16_t a_recovered[256];
    inverse_ntt_256(C_spec, c_poly);
    inverse_ntt_256(A_spec, a_recovered);

    for (int i = 0; i < 256; ++i) {
        uint32_t packed_out = (static_cast<uint16_t>(c_poly[i])) | (static_cast<uint32_t>(static_cast<uint16_t>(a_recovered[i])) << 16);
        out_packed_res[i] = packed_out;
    }
}

}
