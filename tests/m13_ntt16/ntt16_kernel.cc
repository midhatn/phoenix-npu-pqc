
#include <stdint.h>

namespace {

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

// Precomputed powers of omega = 2699 mod 3329:
// omega^0 = 1, omega^1 = 2699, omega^2 = 749, omega^3 = 848,
// omega^4 = 1729, omega^5 = 2642, omega^6 = 40, omega^7 = 1432
static const int16_t W[8] = {
    1, 2699, 749, 848, 1729, 2642, 40, 1432
};

// Bit-reversal permutation for N=16 (4 bits)
static const uint8_t BIT_REV_16[16] = {
    0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15
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

inline void ntt_16_frame(const int16_t* in_frame, int16_t* out_frame) {
    int16_t a[16];

    // 1. Bit-reversal reordering
    for (int i = 0; i < 16; ++i) {
        a[i] = in_frame[BIT_REV_16[i]];
    }

    // Stage 1 (m=2, half_m=1, twiddle: W[0]=1)
    for (int k = 0; k < 16; k += 2) {
        int16_t u = a[k];
        int16_t v = a[k + 1];
        a[k] = mod_add_scalar(u, v);
        a[k + 1] = mod_sub_scalar(u, v);
    }

    // Stage 2 (m=4, half_m=2, twiddles: W[0]=1, W[4]=1729)
    for (int k = 0; k < 16; k += 4) {
        // j = 0: w = 1
        int16_t u0 = a[k];
        int16_t v0 = a[k + 2];
        a[k] = mod_add_scalar(u0, v0);
        a[k + 2] = mod_sub_scalar(u0, v0);

        // j = 1: w = W[4] = 1729 (since (16/4)*1 = 4)
        int16_t u1 = a[k + 1];
        int16_t v1_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 3]) * 1729);
        a[k + 1] = mod_add_scalar(u1, v1_w);
        a[k + 3] = mod_sub_scalar(u1, v1_w);
    }

    // Stage 3 (m=8, half_m=4, twiddles: W[0]=1, W[2]=749, W[4]=1729, W[6]=40)
    for (int k = 0; k < 16; k += 8) {
        // j = 0: w = W[0] = 1
        int16_t u0 = a[k];
        int16_t v0 = a[k + 4];
        a[k] = mod_add_scalar(u0, v0);
        a[k + 4] = mod_sub_scalar(u0, v0);

        // j = 1: w = W[2] = 749
        int16_t u1 = a[k + 1];
        int16_t v1_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 5]) * 749);
        a[k + 1] = mod_add_scalar(u1, v1_w);
        a[k + 5] = mod_sub_scalar(u1, v1_w);

        // j = 2: w = W[4] = 1729
        int16_t u2 = a[k + 2];
        int16_t v2_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 6]) * 1729);
        a[k + 2] = mod_add_scalar(u2, v2_w);
        a[k + 6] = mod_sub_scalar(u2, v2_w);

        // j = 3: w = W[6] = 40
        int16_t u3 = a[k + 3];
        int16_t v3_w = barrett_reduce_scalar(static_cast<int32_t>(a[k + 7]) * 40);
        a[k + 3] = mod_add_scalar(u3, v3_w);
        a[k + 7] = mod_sub_scalar(u3, v3_w);
    }

    // Stage 4 (m=16, half_m=8, twiddles: W[0..7])
    for (int j = 0; j < 8; ++j) {
        int16_t u = a[j];
        int16_t w = W[j];
        int16_t v_w = (j == 0) ? a[j + 8] : barrett_reduce_scalar(static_cast<int32_t>(a[j + 8]) * w);
        out_frame[j] = mod_add_scalar(u, v_w);
        out_frame[j + 8] = mod_sub_scalar(u, v_w);
    }
}

} // anonymous namespace

extern "C" {

void ntt16_kernel(
    const uint32_t* in_packed,
    uint32_t* out_packed
) {
    const int16_t* in_ptr = reinterpret_cast<const int16_t*>(in_packed);
    int16_t* out_ptr = reinterpret_cast<int16_t*>(out_packed);

    // Process 64 parallel 16-point NTT frames (1024 total elements)
    #pragma clang loop unroll_count(4)
    for (int frame = 0; frame < 64; ++frame) {
        ntt_16_frame(in_ptr + frame * 16, out_ptr + frame * 16);
    }
}

}
