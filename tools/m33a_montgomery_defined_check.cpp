// SPDX-License-Identifier: Apache-2.0
//
// Host-side defined-arithmetic check for the actual M33a BASEMUL kernel.
// Compile with UBSan so any signed overflow in the included kernel is fatal:
//   c++ -std=c++17 -fsanitize=undefined -fno-sanitize-recover=undefined
//       tools/m33a_montgomery_defined_check.cpp -o m33a_mont_check
//
// The oracle is independent modular arithmetic:
//   montgomery_reduce(a*b) == a*b*R^-1 (mod q).

#include <cstdint>
#include <cstdio>

#include "../tests/m33_mldsa/dilithium_ntt_kernel.cc"

namespace {

constexpr int32_t TEST_Q = 8380417;
constexpr int32_t TEST_R_INV = 8265825;  // (2^32)^-1 mod q.
constexpr int TEST_N = 256;

int32_t canonical(int32_t value) {
    int64_t reduced = static_cast<int64_t>(value) % TEST_Q;
    if (reduced < 0) {
        reduced += TEST_Q;
    }
    return static_cast<int32_t>(reduced);
}

int32_t expected_product(int32_t a, int32_t b) {
    const uint64_t product =
        (static_cast<uint64_t>(a) * static_cast<uint64_t>(b)) % TEST_Q;
    return static_cast<int32_t>((product * TEST_R_INV) % TEST_Q);
}

}  // namespace

int main() {
    int32_t a[TEST_N] = {};
    int32_t b[TEST_N] = {};
    int32_t out[TEST_N] = {};

    a[0] = TEST_Q - 1;
    b[0] = TEST_Q - 1;
    a[1] = TEST_Q - 1;
    b[1] = TEST_Q - 2;
    a[2] = 0;
    b[2] = TEST_Q - 1;
    a[3] = 1;
    b[3] = 1;

    uint32_t state = 0x4d333361U;
    for (int i = 4; i < TEST_N; ++i) {
        state = state * 1664525U + 1013904223U;
        a[i] = static_cast<int32_t>(state % TEST_Q);
        state = state * 1664525U + 1013904223U;
        b[i] = static_cast<int32_t>(state % TEST_Q);
    }

    int passed = 0;
    for (int i = 0; i < TEST_N; ++i) {
        const int32_t got = canonical(out[i]);
        const int32_t expected = expected_product(a[i], b[i]);
        if (got != expected) {
            std::fprintf(stderr,
                         "FAIL lane=%d a=%d b=%d got=%d expected=%d\n",
                         i, a[i], b[i], got, expected);
            return 1;
        }
        passed++;
    }

    std::printf("M33a Montgomery defined-arithmetic check: %d/%d passed\n", passed, TEST_N);
    return 0;
}
