// SPDX-License-Identifier: Apache-2.0
/**
 * Milestone DR41: Quantum Key Management System (Q-KMS) Integration & Key Lifecycle Engine
 * Internal AIE2 tile definitions, vault slot structures, SP 800-56C Dual KDF,
 * and NIST SP 800-57 / KMIP state machine.
 */

#ifndef PHOENIX_PQC_DR41_QKMS_INTERNAL_HPP
#define PHOENIX_PQC_DR41_QKMS_INTERNAL_HPP

#include <stdint.h>
#include <stddef.h>

#ifdef __AIE2__
#define DR41_INLINE inline __attribute__((always_inline))
#define DR41_NOINLINE __attribute__((noinline))
#define DR41_DISABLE_UNROLL _Pragma("clang loop unroll(disable)")
#else
#define DR41_INLINE inline
#define DR41_NOINLINE
#define DR41_DISABLE_UNROLL
#endif

#ifndef restrict
#define restrict __restrict__
#endif

namespace dr41 {

// Magic & Status
static const uint32_t MAGIC_HEADER               = 0x44523431; // 'DR41'
static const uint32_t STATUS_SUCCESS              = 0x00000000;
static const uint32_t STATUS_ERR_INVALID_MAGIC    = 0x80000001;
static const uint32_t STATUS_ERR_INVALID_SLOT     = 0x80000002;
static const uint32_t STATUS_ERR_ILLEGAL_TRANSITION = 0x80000003;
static const uint32_t STATUS_ERR_SLOT_EXPIRED     = 0x80000004;
static const uint32_t STATUS_ERR_UNSUPPORTED_OP   = 0x80000005;
static const uint32_t STATUS_ERR_KEY_COMPROMISED  = 0x80000006;

// Operations
static const uint32_t OP_VAULT_STORE              = 0x0001;
static const uint32_t OP_VAULT_DERIVE             = 0x0002;
static const uint32_t OP_VAULT_TRANSITION         = 0x0003;
static const uint32_t OP_VAULT_ZEROIZE            = 0x0004;
static const uint32_t OP_VAULT_QUERY              = 0x0005;

// Lifecycle States
static const uint32_t STATE_EMPTY                 = 0;
static const uint32_t STATE_PRE_ACTIVE            = 1;
static const uint32_t STATE_ACTIVE                = 2;
static const uint32_t STATE_DEACTIVATED           = 3;
static const uint32_t STATE_COMPROMISED           = 4;
static const uint32_t STATE_DESTROYED             = 5;

// Key Types
static const uint32_t KEY_TYPE_QKD                = 0x01;
static const uint32_t KEY_TYPE_PQC_SHARED_SECRET  = 0x02;
static const uint32_t KEY_TYPE_DERIVED_SESSION    = 0x03;

static const size_t NUM_VAULT_SLOTS               = 8;

struct TileVaultSlot {
    uint32_t state;
    uint32_t key_type;
    uint8_t  key_id[16];
    uint8_t  key_material[32];
    uint32_t epoch;
};

DR41_INLINE void copy32_bytes(uint8_t* dst, const uint8_t* src) {
    const uint32_t* s32 = (const uint32_t*)src;
    uint32_t* d32 = (uint32_t*)dst;
    DR41_DISABLE_UNROLL
    _Pragma("clang loop vectorize(disable)")
    for (size_t i = 0; i < 8; ++i) {
        d32[i] = s32[i];
    }
}

DR41_INLINE void copy16_bytes(uint8_t* dst, const uint8_t* src) {
    const uint32_t* s32 = (const uint32_t*)src;
    uint32_t* d32 = (uint32_t*)dst;
    DR41_DISABLE_UNROLL
    _Pragma("clang loop vectorize(disable)")
    for (size_t i = 0; i < 4; ++i) {
        d32[i] = s32[i];
    }
}

// Compute slot checksum matching independent oracle
DR41_INLINE uint32_t compute_slot_checksum(const TileVaultSlot* s) {
    uint32_t chk = 0;
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 16; ++i) {
        chk = (chk * 31u + s->key_id[i]) & 0xFFFFFFFFu;
    }
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 32; ++i) {
        chk = (chk * 37u + s->key_material[i]) & 0xFFFFFFFFu;
    }
    chk = (chk + s->state * 101u + s->key_type * 17u + s->epoch) & 0xFFFFFFFFu;
    return chk;
}

// NIST SP 800-57 / KMIP Valid State Transition Gate
DR41_INLINE bool is_valid_transition(uint32_t from_state, uint32_t to_state) {
    if (from_state == STATE_EMPTY) {
        return (to_state == STATE_PRE_ACTIVE || to_state == STATE_ACTIVE);
    }
    if (from_state == STATE_PRE_ACTIVE) {
        return (to_state == STATE_ACTIVE || to_state == STATE_DESTROYED);
    }
    if (from_state == STATE_ACTIVE) {
        return (to_state == STATE_DEACTIVATED || to_state == STATE_COMPROMISED || to_state == STATE_DESTROYED);
    }
    if (from_state == STATE_DEACTIVATED) {
        return (to_state == STATE_COMPROMISED || to_state == STATE_DESTROYED);
    }
    if (from_state == STATE_COMPROMISED) {
        return (to_state == STATE_DESTROYED);
    }
    return false; // STATE_DESTROYED is terminal
}

// -----------------------------------------------------------------------------
// Pure 32-bit SHA-256 Implementation for On-Tile SP 800-56C Dual KDF
// -----------------------------------------------------------------------------

DR41_INLINE uint32_t rotr32(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32u - n));
}

static const uint32_t SHA256_K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

struct Sha256Ctx {
    uint32_t state[8];
    uint32_t count_bytes;
    uint8_t  buf[64];
};

DR41_INLINE void sha256_init(Sha256Ctx* ctx) {
    ctx->state[0] = 0x6a09e667u;
    ctx->state[1] = 0xbb67ae85u;
    ctx->state[2] = 0x3c6ef372u;
    ctx->state[3] = 0xa54ff53au;
    ctx->state[4] = 0x510e527fu;
    ctx->state[5] = 0x9b05688cu;
    ctx->state[6] = 0x1f83d9abu;
    ctx->state[7] = 0x5be0cd19u;
    ctx->count_bytes = 0;
}

DR41_NOINLINE void sha256_transform(Sha256Ctx* ctx, const uint8_t* data) {
    uint32_t w[64];
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 16; ++i) {
        w[i] = ((uint32_t)data[i * 4] << 24) |
               ((uint32_t)data[i * 4 + 1] << 16) |
               ((uint32_t)data[i * 4 + 2] << 8) |
               ((uint32_t)data[i * 4 + 3]);
    }
    DR41_DISABLE_UNROLL
    for (size_t i = 16; i < 64; ++i) {
        uint32_t s0 = rotr32(w[i - 15], 7) ^ rotr32(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr32(w[i - 2], 17) ^ rotr32(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    uint32_t a = ctx->state[0];
    uint32_t b = ctx->state[1];
    uint32_t c = ctx->state[2];
    uint32_t d = ctx->state[3];
    uint32_t e = ctx->state[4];
    uint32_t f = ctx->state[5];
    uint32_t g = ctx->state[6];
    uint32_t h = ctx->state[7];

    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 64; ++i) {
        uint32_t s1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t t1 = h + s1 + ch + SHA256_K[i] + w[i];
        uint32_t s0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = s0 + maj;

        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }

    ctx->state[0] += a;
    ctx->state[1] += b;
    ctx->state[2] += c;
    ctx->state[3] += d;
    ctx->state[4] += e;
    ctx->state[5] += f;
    ctx->state[6] += g;
    ctx->state[7] += h;
}

DR41_INLINE void sha256_update(Sha256Ctx* ctx, const uint8_t* in, size_t len) {
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < len; ++i) {
        ctx->buf[ctx->count_bytes % 64] = in[i];
        ctx->count_bytes++;
        if ((ctx->count_bytes % 64) == 0) {
            sha256_transform(ctx, ctx->buf);
        }
    }
}

DR41_NOINLINE void sha256_final(Sha256Ctx* ctx, uint8_t* out) {
    uint32_t total_bits = ctx->count_bytes * 8u;
    size_t rem = ctx->count_bytes % 64;
    ctx->buf[rem++] = 0x80;
    if (rem > 56) {
        while (rem < 64) ctx->buf[rem++] = 0;
        sha256_transform(ctx, ctx->buf);
        rem = 0;
    }
    while (rem < 56) ctx->buf[rem++] = 0;
    // Append 64-bit length (top 32 bits = 0)
    ctx->buf[56] = 0; ctx->buf[57] = 0; ctx->buf[58] = 0; ctx->buf[59] = 0;
    ctx->buf[60] = (uint8_t)(total_bits >> 24);
    ctx->buf[61] = (uint8_t)(total_bits >> 16);
    ctx->buf[62] = (uint8_t)(total_bits >> 8);
    ctx->buf[63] = (uint8_t)(total_bits);
    sha256_transform(ctx, ctx->buf);

    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 8; ++i) {
        out[i * 4]     = (uint8_t)(ctx->state[i] >> 24);
        out[i * 4 + 1] = (uint8_t)(ctx->state[i] >> 16);
        out[i * 4 + 2] = (uint8_t)(ctx->state[i] >> 8);
        out[i * 4 + 3] = (uint8_t)(ctx->state[i]);
    }
}

DR41_NOINLINE void hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t data_len, uint8_t* out) {
    uint8_t k_pad[64];
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 64; ++i) {
        k_pad[i] = (i < key_len) ? key[i] : 0;
    }

    uint8_t ipad[64];
    uint8_t opad[64];
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 64; ++i) {
        ipad[i] = k_pad[i] ^ 0x36;
        opad[i] = k_pad[i] ^ 0x5C;
    }

    Sha256Ctx ctx;
    uint8_t inner_hash[32];
    sha256_init(&ctx);
    sha256_update(&ctx, ipad, 64);
    sha256_update(&ctx, data, data_len);
    sha256_final(&ctx, inner_hash);

    sha256_init(&ctx);
    sha256_update(&ctx, opad, 64);
    sha256_update(&ctx, inner_hash, 32);
    sha256_final(&ctx, out);
}

// SP 800-56C Dual KDF: Extract PRK = HMAC(salt, pqc_secret || qkd_key), Expand OKM = HMAC(PRK, info || 0x01)
DR41_NOINLINE void sp800_56c_dual_kdf(
    const uint8_t* pqc_secret,
    const uint8_t* qkd_key,
    const uint8_t* context_salt,
    uint8_t* out_session_key
) {
    // 1. Extract Step
    uint8_t ikm[64];
    DR41_DISABLE_UNROLL
    for (size_t i = 0; i < 32; ++i) {
        ikm[i]      = pqc_secret[i];
        ikm[i + 32] = qkd_key[i];
    }
    uint8_t prk[32];
    hmac_sha256(context_salt, 32, ikm, 64, prk);

    // 2. Expand Step: info = "SP800-56C-DUAL-KDF\x01" (19 bytes)
    static const uint8_t INFO[19] = {
        'S','P','8','0','0','-','5','6','C','-','D','U','A','L','-','K','D','F', 0x01
    };
    hmac_sha256(prk, 32, INFO, 19, out_session_key);
}

} // namespace dr41

#endif // PHOENIX_PQC_DR41_QKMS_INTERNAL_HPP
