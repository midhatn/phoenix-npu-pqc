
#include <stdint.h>

#define MOD 3329
#define N 256
#define BARRETT_MU 20165
#define BARRETT_SHIFT 26

static inline int32_t barrett_reduce(int32_t val) {
    int32_t q_val = (int32_t)(((int64_t)val * BARRETT_MU) >> BARRETT_SHIFT);
    int32_t res = val - q_val * MOD;
    if (res >= MOD) res -= MOD;
    if (res < 0) res += MOD;
    return res;
}

static inline int32_t mod_add(int32_t a, int32_t b) {
    int32_t res = a + b;
    if (res >= MOD) res -= MOD;
    return res;
}

static inline int32_t mod_sub(int32_t a, int32_t b) {
    int32_t res = a - b;
    if (res < 0) res += MOD;
    return res;
}

static inline int32_t mod_mul(int32_t a, int32_t b) {
    return barrett_reduce(a * b);
}

extern "C" {

// C(x) = A(x) * B(x) mod (x^256 + 1, 3329)
void negacyclic_polymul_kernel(
    const uint32_t* restrict in_a,
    const uint32_t* restrict in_b,
    uint32_t* restrict out_c
) {
    static int32_t c_acc[N];
    for (int i = 0; i < N; i++) {
        c_acc[i] = 0;
    }

    for (int i = 0; i < N; i++) {
        int32_t ai = in_a[i];
        if (ai == 0) continue;
        for (int j = 0; j < N; j++) {
            int32_t term = mod_mul(ai, in_b[j]);
            int deg = i + j;
            if (deg < N) {
                c_acc[deg] = mod_add(c_acc[deg], term);
            } else {
                c_acc[deg - N] = mod_sub(c_acc[deg - N], term);
            }
        }
    }

    for (int i = 0; i < N; i++) {
        out_c[i] = c_acc[i];
    }
}

}
