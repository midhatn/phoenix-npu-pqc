
#include <stdint.h>

static constexpr int16_t MOD_Q = 3329;
static constexpr int32_t BARRETT_FACTOR = 20158;
static constexpr int32_t BARRETT_SHIFT = 26;

inline int16_t mod_add_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) + static_cast<int32_t>(b);
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

inline int16_t mod_sub_scalar(int16_t a, int16_t b, int16_t q = MOD_Q) {
    int32_t res = static_cast<int32_t>(a) - static_cast<int32_t>(b);
    if (res < 0) res += q;
    return static_cast<int16_t>(res);
}

inline int16_t barrett_reduce_scalar(int32_t a, int16_t q = MOD_Q) {
    int32_t t = static_cast<int32_t>((static_cast<int64_t>(a) * BARRETT_FACTOR) >> BARRETT_SHIFT);
    int32_t res = a - t * q;
    if (res >= q) res -= q;
    return static_cast<int16_t>(res);
}

inline void ct_butterfly(int16_t u, int16_t v, int16_t omega, int16_t& u_out, int16_t& v_out, int16_t q = MOD_Q) {
    int32_t prod = static_cast<int32_t>(v) * static_cast<int32_t>(omega);
    int16_t v_w = barrett_reduce_scalar(prod, q);

    u_out = mod_add_scalar(u, v_w, q);
    v_out = mod_sub_scalar(u, v_w, q);
}

extern "C" {

void ntt_butterfly_kernel(
    const uint32_t* in_packed_uv,
    const uint32_t* in_twiddles,
    uint32_t* out_packed_res
) {
    #pragma clang loop unroll_count(8)
    for (int32_t i = 0; i < 1024; ++i) {
        uint32_t uv = in_packed_uv[i];
        int16_t u = static_cast<int16_t>(uv & 0xFFFF);
        int16_t v = static_cast<int16_t>((uv >> 16) & 0xFFFF);
        int16_t omega = static_cast<int16_t>(in_twiddles[i] & 0xFFFF);

        int16_t u_out, v_out;
        ct_butterfly(u, v, omega, u_out, v_out);

        uint32_t packed_out = (static_cast<uint16_t>(u_out)) | (static_cast<uint32_t>(static_cast<uint16_t>(v_out)) << 16);
        out_packed_res[i] = packed_out;
    }
}

}
