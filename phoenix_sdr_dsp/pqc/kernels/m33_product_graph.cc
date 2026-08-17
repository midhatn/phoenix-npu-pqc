// SPDX-License-Identifier: Apache-2.0
// DR0 terminal-only ML-DSA polynomial product on one Phoenix AIE2 tile.
//
// The required M33a constants and transform arithmetic are production-local in
// m33a_arithmetic.hpp.  This compilation unit has no test-tree include or other
// runtime/compile-time dependency on test artifacts.  The sole AIE entry owns
// all temporary NTT-domain state:
//   c = INTT(BASEMUL(NTT(a), NTT(b))) mod (X^256 + 1, q).
//
// Host ABI: exactly two 256 x int32 ingress buffers (a, b) and one 256 x int32
// terminal egress buffer (c).  There is no mode/control FIFO, no intermediate
// ObjectFIFO, and no host-side Montgomery rescale.

#include <cstdint>

#include "m33a_arithmetic.hpp"

namespace m33a = phoenix_sdr_dsp::pqc::m33a;

extern "C" {

void m33_product_graph(int32_t in_a[m33a::N],
                       int32_t in_b[m33a::N],
                       int32_t out_c[m33a::N]) {
    // 3 KiB total local data: two transform workspaces plus one base-product.
    // This is well below Phoenix AIE2's 64 KiB tile-local-memory budget.
    int32_t a_ntt[m33a::N];
    int32_t b_ntt[m33a::N];
    int32_t product_ntt[m33a::N];

    for (int32_t i = 0; i < m33a::N; ++i) {
        a_ntt[i] = in_a[i];
        b_ntt[i] = in_b[i];
    }

    // Exact M33a arithmetic and scaling convention:
    // NTT is plain-domain, BASEMUL contributes R^-1, and INTT contributes R.
    // The factors cancel entirely on the device before the terminal write.
    m33a::ntt_kernel(a_ntt);
    m33a::ntt_kernel(b_ntt);
    m33a::basemul_kernel(product_ntt, a_ntt, b_ntt);
    m33a::invntt_kernel(product_ntt);

    // Canonicalize on the AIE.  Do not expose an implicit Montgomery factor or
    // a signed residue to the host.  int64_t prevents a signed division edge
    // case while retaining the production-local M33a transform arithmetic.
    for (int32_t i = 0; i < m33a::N; ++i) {
        int64_t value = static_cast<int64_t>(product_ntt[i]) % m33a::Q;
        if (value < 0) value += m33a::Q;
        out_c[i] = static_cast<int32_t>(value);
    }
}

}  // extern "C"
