// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR28: NIST SP 800-208 / RFC 8554 LMS Stateless Verification
 * Micro-architecture and cryptographic hash verification primitives for AMD Phoenix AIE2 (XDNA1).
 */
#ifndef DR28_LMS_VERIFIER_INTERNAL_HPP
#define DR28_LMS_VERIFIER_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR28_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr28 {

// RFC 8554 Domain Separators
static const uint16_t D_PKEY = 0x0080;
static const uint16_t D_INTR = 0x0081;
static const uint16_t D_LEAF = 0x0082;
static const uint16_t D_MESG = 0x0083;

static inline uint32_t rotr32(uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

// SHA-256 Constants
static const uint32_t SHA256_K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

__attribute__((noinline))
static void sha256_transform(uint32_t state[8], const uint8_t data[64]) {
    uint32_t m[64];
    DR28_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) {
        m[i] = ((uint32_t)data[i * 4] << 24) |
               ((uint32_t)data[i * 4 + 1] << 16) |
               ((uint32_t)data[i * 4 + 2] << 8) |
               ((uint32_t)data[i * 4 + 3]);
    }
    DR28_DISABLE_UNROLL
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr32(m[i - 15], 7) ^ rotr32(m[i - 15], 18) ^ (m[i - 15] >> 3);
        uint32_t s1 = rotr32(m[i - 2], 17) ^ rotr32(m[i - 2], 19) ^ (m[i - 2] >> 10);
        m[i] = m[i - 16] + s0 + m[i - 7] + s1;
    }

    uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
    uint32_t e = state[4], f = state[5], g = state[6], h = state[7];

    DR28_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) {
        uint32_t S1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + S1 + ch + SHA256_K[i] + m[i];
        uint32_t S0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = S0 + maj;

        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

__attribute__((noinline))
static void sha256(const uint8_t* in, size_t in_len, uint8_t out[32]) {
    uint32_t state[8] = {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
    };

    uint8_t buffer[64];
    size_t offset = 0;

    while (in_len >= 64) {
        sha256_transform(state, in);
        in += 64;
        in_len -= 64;
        offset += 64;
    }

    // Padding
    DR28_DISABLE_UNROLL
    for (size_t i = 0; i < in_len; ++i) buffer[i] = in[i];
    buffer[in_len] = 0x80;
    offset += in_len;

    if (in_len < 56) {
        DR28_DISABLE_UNROLL
        for (size_t i = in_len + 1; i < 56; ++i) buffer[i] = 0;
    } else {
        DR28_DISABLE_UNROLL
        for (size_t i = in_len + 1; i < 64; ++i) buffer[i] = 0;
        sha256_transform(state, buffer);
        DR28_DISABLE_UNROLL
        for (size_t i = 0; i < 56; ++i) buffer[i] = 0;
    }

    uint64_t total_bits = (uint64_t)offset * 8;
    for (int i = 0; i < 8; ++i) {
        buffer[56 + i] = (uint8_t)((total_bits >> (56 - 8 * i)) & 0xFF);
    }
    sha256_transform(state, buffer);

    DR28_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) {
        out[i * 4]     = (uint8_t)((state[i] >> 24) & 0xFF);
        out[i * 4 + 1] = (uint8_t)((state[i] >> 16) & 0xFF);
        out[i * 4 + 2] = (uint8_t)((state[i] >> 8) & 0xFF);
        out[i * 4 + 3] = (uint8_t)(state[i] & 0xFF);
    }
}

// Multi-chunk SHA-256 for composite hash evaluation
__attribute__((noinline))
static void sha256_chunks(const uint8_t* const chunks[], const size_t lens[], size_t num_chunks, uint8_t out[32]) {
    // Total buffer assembly for chunk inputs up to 2500 bytes
    uint8_t full_buf[2500];
    size_t total = 0;
    DR28_DISABLE_UNROLL
    for (size_t c = 0; c < num_chunks; ++c) {
        for (size_t i = 0; i < lens[c]; ++i) {
            full_buf[total + i] = chunks[c][i];
        }
        total += lens[c];
    }
    sha256(full_buf, total, out);
}

// LM-OTS Verification and Candidate Leaf Recovery (RFC 8554 Algorithm 4b)
__attribute__((noinline))
static int lm_ots_recover_leaf(
    const uint8_t I[16],
    uint32_t q,
    const uint8_t C[32],
    const uint8_t* y_sigs, // 67 * 32 bytes
    const uint8_t* msg,
    size_t msg_len,
    uint8_t out_kc[32]
) {
    // 1. Compute Q = SHA256(I || q || D_MESG || C || msg)
    uint8_t q_hdr[22];
    for (int i = 0; i < 16; ++i) q_hdr[i] = I[i];
    q_hdr[16] = (uint8_t)((q >> 24) & 0xFF);
    q_hdr[17] = (uint8_t)((q >> 16) & 0xFF);
    q_hdr[18] = (uint8_t)((q >> 8) & 0xFF);
    q_hdr[19] = (uint8_t)(q & 0xFF);
    q_hdr[20] = (uint8_t)((D_MESG >> 8) & 0xFF);
    q_hdr[21] = (uint8_t)(D_MESG & 0xFF);

    const uint8_t* q_chunks[3] = { q_hdr, C, msg };
    const size_t q_lens[3] = { 22, 32, msg_len };
    uint8_t Q[32];
    sha256_chunks(q_chunks, q_lens, 3, Q);

    // 2. Extract digits and compute Winternitz checksum (w=4)
    uint8_t a[67];
    uint16_t csum = 0;
    DR28_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) {
        uint8_t hi = (Q[i] >> 4) & 0x0F;
        uint8_t lo = Q[i] & 0x0F;
        a[2 * i] = hi;
        a[2 * i + 1] = lo;
        csum += (15 - hi);
        csum += (15 - lo);
    }
    csum <<= 4; // Shift for ls=4
    a[64] = (uint8_t)((csum >> 12) & 0x0F);
    a[65] = (uint8_t)((csum >> 8) & 0x0F);
    a[66] = (uint8_t)((csum >> 4) & 0x0F);

    // 3. Iterate hash chains forward
    uint8_t z_all[67 * 32];
    uint8_t chain_prefix[22];
    for (int i = 0; i < 16; ++i) chain_prefix[i] = I[i];
    chain_prefix[16] = (uint8_t)((q >> 24) & 0xFF);
    chain_prefix[17] = (uint8_t)((q >> 16) & 0xFF);
    chain_prefix[18] = (uint8_t)((q >> 8) & 0xFF);
    chain_prefix[19] = (uint8_t)(q & 0xFF);

    DR28_DISABLE_UNROLL
    for (int i = 0; i < 67; ++i) {
        chain_prefix[20] = (uint8_t)((i >> 8) & 0xFF);
        chain_prefix[21] = (uint8_t)(i & 0xFF);

        uint8_t cur_val[32];
        for (int k = 0; k < 32; ++k) cur_val[k] = y_sigs[i * 32 + k];

        for (uint8_t j = a[i]; j < 15; ++j) {
            uint8_t step_hdr[23];
            for (int k = 0; k < 22; ++k) step_hdr[k] = chain_prefix[k];
            step_hdr[22] = j;

            const uint8_t* st_chunks[2] = { step_hdr, cur_val };
            const size_t st_lens[2] = { 23, 32 };
            sha256_chunks(st_chunks, st_lens, 2, cur_val);
        }
        for (int k = 0; k < 32; ++k) z_all[i * 32 + k] = cur_val[k];
    }

    // 4. Compute candidate public key Kc = SHA256(I || q || D_PKEY || z[0..66])
    uint8_t pkey_hdr[22];
    for (int i = 0; i < 16; ++i) pkey_hdr[i] = I[i];
    pkey_hdr[16] = (uint8_t)((q >> 24) & 0xFF);
    pkey_hdr[17] = (uint8_t)((q >> 16) & 0xFF);
    pkey_hdr[18] = (uint8_t)((q >> 8) & 0xFF);
    pkey_hdr[19] = (uint8_t)(q & 0xFF);
    pkey_hdr[20] = (uint8_t)((D_PKEY >> 8) & 0xFF);
    pkey_hdr[21] = (uint8_t)(D_PKEY & 0xFF);

    const uint8_t* pk_chunks[2] = { pkey_hdr, z_all };
    const size_t pk_lens[2] = { 22, 67 * 32 };
    sha256_chunks(pk_chunks, pk_lens, 2, out_kc);
    return 0;
}

// Merkle Path Traversal (RFC 8554 Algorithm 6b)
__attribute__((noinline))
static void lms_traverse_path(
    const uint8_t I[16],
    uint32_t q,
    const uint8_t leaf_kc[32],
    const uint8_t* auth_path, // h * 32 bytes
    uint32_t h,
    uint8_t out_root[32]
) {
    // 1. Compute leaf node T[2^h + q] = SHA256(I || (2^h + q) || D_LEAF || Kc)
    uint32_t node_id = (1u << h) + q;
    uint8_t leaf_hdr[22];
    for (int i = 0; i < 16; ++i) leaf_hdr[i] = I[i];
    leaf_hdr[16] = (uint8_t)((node_id >> 24) & 0xFF);
    leaf_hdr[17] = (uint8_t)((node_id >> 16) & 0xFF);
    leaf_hdr[18] = (uint8_t)((node_id >> 8) & 0xFF);
    leaf_hdr[19] = (uint8_t)(node_id & 0xFF);
    leaf_hdr[20] = (uint8_t)((D_LEAF >> 8) & 0xFF);
    leaf_hdr[21] = (uint8_t)(D_LEAF & 0xFF);

    const uint8_t* lf_chunks[2] = { leaf_hdr, leaf_kc };
    const size_t lf_lens[2] = { 22, 32 };
    uint8_t cur_node[32];
    sha256_chunks(lf_chunks, lf_lens, 2, cur_node);

    // 2. Ascend tree to root
    DR28_DISABLE_UNROLL
    for (uint32_t i = 0; i < h; ++i) {
        uint32_t parent_id = node_id / 2;
        uint8_t intr_hdr[22];
        for (int k = 0; k < 16; ++k) intr_hdr[k] = I[k];
        intr_hdr[16] = (uint8_t)((parent_id >> 24) & 0xFF);
        intr_hdr[17] = (uint8_t)((parent_id >> 16) & 0xFF);
        intr_hdr[18] = (uint8_t)((parent_id >> 8) & 0xFF);
        intr_hdr[19] = (uint8_t)(parent_id & 0xFF);
        intr_hdr[20] = (uint8_t)((D_INTR >> 8) & 0xFF);
        intr_hdr[21] = (uint8_t)(D_INTR & 0xFF);

        const uint8_t* sibling = auth_path + i * 32;
        uint8_t next_node[32];

        if (node_id % 2 == 1) {
            // Sibling is left, cur_node is right
            const uint8_t* in_chunks[3] = { intr_hdr, sibling, cur_node };
            const size_t in_lens[3] = { 22, 32, 32 };
            sha256_chunks(in_chunks, in_lens, 3, next_node);
        } else {
            // cur_node is left, Sibling is right
            const uint8_t* in_chunks[3] = { intr_hdr, cur_node, sibling };
            const size_t in_lens[3] = { 22, 32, 32 };
            sha256_chunks(in_chunks, in_lens, 3, next_node);
        }
        for (int k = 0; k < 32; ++k) cur_node[k] = next_node[k];
        node_id = parent_id;
    }

    for (int k = 0; k < 32; ++k) out_root[k] = cur_node[k];
}

} // namespace dr28

#endif // DR28_LMS_VERIFIER_INTERNAL_HPP
