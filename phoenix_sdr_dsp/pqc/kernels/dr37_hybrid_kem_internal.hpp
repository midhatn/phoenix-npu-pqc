// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR37: Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine
 * Micro-architecture and normative cryptographic combiner for AMD Phoenix AIE2 (XDNA1).
 * Compliant with ETSI TS 103 744, BSI TR-02102-1, IETF RFC 9180 (HPKE), and NIST SP 800-56C Rev. 2.
 */
#ifndef DR37_HYBRID_KEM_INTERNAL_HPP
#define DR37_HYBRID_KEM_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#define DR37_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")

namespace dr37 {

// Architectural Constants & Magic
static const uint32_t MAGIC_HEADER = 0x454B3701; // "\x017KE"
static const uint32_t MAGIC_RESULT = 0x3733454B; // "KE37"

// Operation Modes
enum OpMode : uint32_t {
    MODE_HYBRID_ENCAPS_COMBINE = 1,
    MODE_HYBRID_DECAPS_COMBINE = 2,
    MODE_HYBRID_SPLIT_SECRET   = 3,
    MODE_HYBRID_POLICY_ENFORCE = 4,
    MODE_HYBRID_ZEROIZE        = 5,
};

// Profile Identifiers
enum ProfileId : uint32_t {
    PROFILE_X25519_MLKEM768     = 1,
    PROFILE_SECP384R1_MLKEM1024 = 2,
};

// Status Return Codes
enum StatusCode : uint32_t {
    STATUS_SUCCESS              = 0,
    STATUS_ERR_INVALID_MAGIC    = 1,
    STATUS_ERR_DEGENERATE_KEY   = 2,
    STATUS_ERR_POLICY_VIOLATION = 3,
    STATUS_ERR_INVALID_PROFILE  = 4,
    STATUS_ERR_INTEGRITY_FAIL   = 5,
};

// Buffer Geometries (32-byte aligned for AIE2 ObjectFifo)
static const size_t DESC_TOTAL_BYTES   = 64;
static const size_t REQ_TOTAL_BYTES    = 16384;
static const size_t RESULT_TOTAL_BYTES = 2048;

static inline uint32_t rotr32(uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

// Constant-time memory comparison
__attribute__((noinline))
static int ct_compare(const uint8_t* a, const uint8_t* b, size_t len) {
    uint8_t diff = 0;
    DR37_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        diff |= (a[i] ^ b[i]);
    }
    return (diff == 0) ? 1 : 0;
}

// Constant-time check if all bytes are zero
__attribute__((noinline))
static int ct_is_all_zero(const uint8_t* buf, size_t len) {
    uint8_t acc = 0;
    DR37_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        acc |= buf[i];
    }
    return (acc == 0) ? 1 : 0;
}

// Constant-time memory zeroization
__attribute__((noinline))
static void secure_zeroize(uint8_t* buf, size_t len) {
    volatile uint8_t* p = (volatile uint8_t*)buf;
    DR37_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        p[i] = 0;
    }
}

// =========================================================================
// Normative NIST FIPS 180-4 SHA-256 Implementation
// =========================================================================

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

struct Sha256Ctx {
    uint32_t state[8];
    uint8_t buffer[64];
    uint64_t total_bits;
    size_t buf_len;
};

__attribute__((noinline))
static void sha256_transform(uint32_t state[8], const uint8_t data[64]) {
    uint32_t m[64];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 16; ++i) {
        m[i] = ((uint32_t)data[i * 4] << 24) |
               ((uint32_t)data[i * 4 + 1] << 16) |
               ((uint32_t)data[i * 4 + 2] << 8) |
               ((uint32_t)data[i * 4 + 3]);
    }
    DR37_DISABLE_UNROLL
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr32(m[i - 15], 7) ^ rotr32(m[i - 15], 18) ^ (m[i - 15] >> 3);
        uint32_t s1 = rotr32(m[i - 2], 17) ^ rotr32(m[i - 2], 19) ^ (m[i - 2] >> 10);
        m[i] = m[i - 16] + s0 + m[i - 7] + s1;
    }

    uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
    uint32_t e = state[4], f = state[5], g = state[6], h = state[7];

    DR37_DISABLE_UNROLL
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
static void sha256_init(Sha256Ctx* ctx) {
    ctx->state[0] = 0x6a09e667;
    ctx->state[1] = 0xbb67ae85;
    ctx->state[2] = 0x3c6ef372;
    ctx->state[3] = 0xa54ff53a;
    ctx->state[4] = 0x510e527f;
    ctx->state[5] = 0x9b05688c;
    ctx->state[6] = 0x1f83d9ab;
    ctx->state[7] = 0x5be0cd19;
    ctx->total_bits = 0;
    ctx->buf_len = 0;
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) ctx->buffer[i] = 0;
}

__attribute__((noinline))
static void sha256_update(Sha256Ctx* ctx, const uint8_t* data, size_t len) {
    ctx->total_bits += (uint64_t)len * 8;

    if (ctx->buf_len > 0) {
        size_t needed = 64 - ctx->buf_len;
        size_t take = (len < needed) ? len : needed;
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < take; ++i) {
            ctx->buffer[ctx->buf_len + i] = data[i];
        }
        ctx->buf_len += take;
        data += take;
        len -= take;

        if (ctx->buf_len == 64) {
            sha256_transform(ctx->state, ctx->buffer);
            ctx->buf_len = 0;
        }
    }

    while (len >= 64) {
        sha256_transform(ctx->state, data);
        data += 64;
        len -= 64;
    }

    if (len > 0) {
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < len; ++i) {
            ctx->buffer[i] = data[i];
        }
        ctx->buf_len = len;
    }
}

__attribute__((noinline))
static void sha256_final(Sha256Ctx* ctx, uint8_t out[32]) {
    ctx->buffer[ctx->buf_len++] = 0x80;

    if (ctx->buf_len > 56) {
        DR37_DISABLE_UNROLL
        for (size_t i = ctx->buf_len; i < 64; ++i) ctx->buffer[i] = 0;
        sha256_transform(ctx->state, ctx->buffer);
        ctx->buf_len = 0;
    }

    DR37_DISABLE_UNROLL
    for (size_t i = ctx->buf_len; i < 56; ++i) ctx->buffer[i] = 0;

    for (int i = 0; i < 8; ++i) {
        ctx->buffer[56 + i] = (uint8_t)((ctx->total_bits >> (56 - 8 * i)) & 0xFF);
    }
    sha256_transform(ctx->state, ctx->buffer);

    DR37_DISABLE_UNROLL
    for (int i = 0; i < 8; ++i) {
        out[i * 4]     = (uint8_t)((ctx->state[i] >> 24) & 0xFF);
        out[i * 4 + 1] = (uint8_t)((ctx->state[i] >> 16) & 0xFF);
        out[i * 4 + 2] = (uint8_t)((ctx->state[i] >> 8) & 0xFF);
        out[i * 4 + 3] = (uint8_t)(ctx->state[i] & 0xFF);
    }
}

__attribute__((noinline))
static void sha256(const uint8_t* in, size_t in_len, uint8_t out[32]) {
    Sha256Ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, in, in_len);
    sha256_final(&ctx, out);
}

// =========================================================================
// Normative FIPS 198-1 HMAC-SHA256 Implementation
// =========================================================================

__attribute__((noinline))
static void hmac_sha256(
    const uint8_t* key, size_t key_len,
    const uint8_t* data, size_t data_len,
    uint8_t out[32]
) {
    uint8_t k_pad[64];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) k_pad[i] = 0;

    if (key_len > 64) {
        sha256(key, key_len, k_pad);
    } else {
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < key_len; ++i) k_pad[i] = key[i];
    }

    uint8_t ipad[64], opad[64];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) {
        ipad[i] = k_pad[i] ^ 0x36;
        opad[i] = k_pad[i] ^ 0x5c;
    }

    uint8_t inner_hash[32];
    Sha256Ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, ipad, 64);
    sha256_update(&ctx, data, data_len);
    sha256_final(&ctx, inner_hash);

    sha256_init(&ctx);
    sha256_update(&ctx, opad, 64);
    sha256_update(&ctx, inner_hash, 32);
    sha256_final(&ctx, out);

    secure_zeroize(k_pad, sizeof(k_pad));
    secure_zeroize(ipad, sizeof(ipad));
    secure_zeroize(opad, sizeof(opad));
    secure_zeroize(inner_hash, sizeof(inner_hash));
}

__attribute__((noinline))
static void hmac_sha256_2parts(
    const uint8_t* key, size_t key_len,
    const uint8_t* data1, size_t data1_len,
    const uint8_t* data2, size_t data2_len,
    uint8_t out[32]
) {
    uint8_t k_pad[64];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) k_pad[i] = 0;

    if (key_len > 64) {
        sha256(key, key_len, k_pad);
    } else {
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < key_len; ++i) k_pad[i] = key[i];
    }

    uint8_t ipad[64], opad[64];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 64; ++i) {
        ipad[i] = k_pad[i] ^ 0x36;
        opad[i] = k_pad[i] ^ 0x5c;
    }

    uint8_t inner_hash[32];
    Sha256Ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, ipad, 64);
    if (data1_len > 0) sha256_update(&ctx, data1, data1_len);
    if (data2_len > 0) sha256_update(&ctx, data2, data2_len);
    sha256_final(&ctx, inner_hash);

    sha256_init(&ctx);
    sha256_update(&ctx, opad, 64);
    sha256_update(&ctx, inner_hash, 32);
    sha256_final(&ctx, out);

    secure_zeroize(k_pad, sizeof(k_pad));
    secure_zeroize(ipad, sizeof(ipad));
    secure_zeroize(opad, sizeof(opad));
    secure_zeroize(inner_hash, sizeof(inner_hash));
}

// =========================================================================
// RFC 5869 / NIST SP 800-56C Rev. 2 HKDF Implementation
// =========================================================================

__attribute__((noinline))
static void hkdf_extract(
    const uint8_t* salt, size_t salt_len,
    const uint8_t* ikm, size_t ikm_len,
    uint8_t prk[32]
) {
    uint8_t default_salt[32];
    const uint8_t* effective_salt = salt;
    size_t effective_salt_len = salt_len;

    if (salt == NULL || salt_len == 0) {
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 32; ++i) default_salt[i] = 0;
        effective_salt = default_salt;
        effective_salt_len = 32;
    }

    hmac_sha256(effective_salt, effective_salt_len, ikm, ikm_len, prk);
}

__attribute__((noinline))
static void hkdf_expand_112(
    const uint8_t prk[32],
    const uint8_t* info, size_t info_len,
    uint8_t out_ss[32],
    uint8_t out_enc[32],
    uint8_t out_mac[32],
    uint8_t out_iv[16]
) {
    uint8_t t[32];
    uint8_t block_counter;

    // Block 1 -> out_ss (32 bytes)
    block_counter = 1;
    hmac_sha256_2parts(prk, 32, info, info_len, &block_counter, 1, t);
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) out_ss[i] = t[i];

    // Block 2 -> out_enc (32 bytes)
    block_counter = 2;
    {
        uint8_t t_and_info[128];
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 32; ++i) t_and_info[i] = t[i];
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < info_len; ++i) t_and_info[32 + i] = info[i];
        hmac_sha256_2parts(prk, 32, t_and_info, 32 + info_len, &block_counter, 1, t);
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 32; ++i) out_enc[i] = t[i];
    }

    // Block 3 -> out_mac (32 bytes)
    block_counter = 3;
    {
        uint8_t t_and_info[128];
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 32; ++i) t_and_info[i] = t[i];
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < info_len; ++i) t_and_info[32 + i] = info[i];
        hmac_sha256_2parts(prk, 32, t_and_info, 32 + info_len, &block_counter, 1, t);
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 32; ++i) out_mac[i] = t[i];
    }

    // Block 4 -> out_iv (16 bytes)
    block_counter = 4;
    {
        uint8_t t_and_info[128];
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 32; ++i) t_and_info[i] = t[i];
        DR37_DISABLE_UNROLL
        for (size_t i = 0; i < info_len; ++i) t_and_info[32 + i] = info[i];
        hmac_sha256_2parts(prk, 32, t_and_info, 32 + info_len, &block_counter, 1, t);
        DR37_DISABLE_UNROLL
        for (int i = 0; i < 16; ++i) out_iv[i] = t[i];
    }

    secure_zeroize(t, sizeof(t));
}

// =========================================================================
// ETSI TS 103 744 / BSI TR-02102-1 Hybrid Combiner Engine
// =========================================================================

__attribute__((noinline))
static int combine_hybrid_keys(
    uint32_t profile_id,
    const uint8_t* classical_ss,
    const uint8_t* pqc_ss,
    const uint8_t* classical_ct,
    const uint8_t* salt,
    const uint8_t* pqc_ct, size_t ct_pqc_len,
    uint8_t* out_final_ss,
    uint8_t* out_enc_key,
    uint8_t* out_mac_key,
    uint8_t* out_iv,
    uint8_t* out_transcript_digest
) {
    // 1. Compute transcript binding: H(CT_pqc) then H(CT_c || H(CT_pqc))
    uint8_t h_pqc_ct[32];
    sha256(pqc_ct, ct_pqc_len, h_pqc_ct);

    Sha256Ctx tctx;
    sha256_init(&tctx);
    sha256_update(&tctx, classical_ct, 32);
    sha256_update(&tctx, h_pqc_ct, 32);
    sha256_final(&tctx, out_transcript_digest);

    // 2. Form IKM = classical_ss || pqc_ss (64 bytes)
    uint8_t ikm[64];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) {
        ikm[i] = classical_ss[i];
        ikm[32 + i] = pqc_ss[i];
    }

    // 3. Form Info = "ETSI_HYBRID_KEM_TS_103_744" (26 bytes) || transcript_digest (32 bytes)
    static const char ETSI_LABEL[] = "ETSI_HYBRID_KEM_TS_103_744";
    uint8_t info[58];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 26; ++i) info[i] = (uint8_t)ETSI_LABEL[i];
    DR37_DISABLE_UNROLL
    for (int i = 0; i < 32; ++i) info[26 + i] = out_transcript_digest[i];

    // 4. HKDF-Extract (salt, IKM) -> PRK
    uint8_t prk[32];
    hkdf_extract(salt, 32, ikm, 64, prk);

    // 5. HKDF-Expand (PRK, Info, 112) -> (final_ss, enc_key, mac_key, iv)
    hkdf_expand_112(prk, info, 58, out_final_ss, out_enc_key, out_mac_key, out_iv);

    secure_zeroize(ikm, sizeof(ikm));
    secure_zeroize(prk, sizeof(prk));
    secure_zeroize(h_pqc_ct, sizeof(h_pqc_ct));

    return 0;
}

} // namespace dr37

#endif // DR37_HYBRID_KEM_INTERNAL_HPP
