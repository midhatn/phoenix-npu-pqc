// SPDX-License-Identifier: Apache-2.0
#include "dr5_mlkem512_keygen_internal.hpp"
#include <stdint.h>

namespace {

static void cbd3(const uint8_t *in, uint32_t *out) {
    DR5_DISABLE_UNROLL
    for (uint32_t i = 0; i < 64; ++i) {
        const uint32_t b0 = in[3 * i + 0];
        const uint32_t b1 = in[3 * i + 1];
        const uint32_t b2 = in[3 * i + 2];
        const uint32_t t = b0 | (b1 << 8) | (b2 << 16);
        uint32_t d = t & 0x00249249u;
        d += (t >> 1) & 0x00249249u;
        d += (t >> 2) & 0x00249249u;
        
        for (uint32_t j = 0; j < 4; ++j) {
            const uint32_t a = (d >> (6 * j)) & 0x07u;
            const uint32_t b = (d >> (6 * j + 3)) & 0x07u;
            out[4 * i + j] = a >= b ? a - b : a + mlkem512_dr5::kQ - b;
        }
    }
}

static void shake256_prf(const uint8_t sigma[32], uint8_t nonce, uint8_t out[192]) {
    alignas(8) uint8_t state[200];
    mlkem512_dr5::clear_bytes(state, sizeof(state));
    for (uint32_t i = 0; i < 32; ++i) state[i] ^= sigma[i];
    state[32] ^= nonce;
    state[33] ^= 0x1F; // SHAKE domain separation
    state[135] ^= 0x80;
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    
    // First 136 bytes
    for (uint32_t i = 0; i < 136; ++i) out[i] = state[i];
    // Squeeze second block
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    for (uint32_t i = 0; i < 56; ++i) out[136 + i] = state[i];
    mlkem512_dr5::clear_bytes(state, sizeof(state));
}

static void sample_cbd3_ntt_store(const uint8_t sigma[32], uint8_t nonce, uint8_t *out) {
    uint8_t prf[192];
    uint32_t coeff[mlkem512_dr5::kN];
    shake256_prf(sigma, nonce, prf);
    cbd3(prf, coeff);
    mlkem512_dr5::forward_ntt(coeff);
    DR5_DISABLE_UNROLL
    for (uint32_t pair = 0; pair < mlkem512_dr5::kN / 2; ++pair) {
        mlkem512_dr5::store_pair_word(out, pair, coeff[2 * pair], coeff[2 * pair + 1]);
    }
    mlkem512_dr5::clear_bytes(prf, sizeof(prf));
    mlkem512_dr5::clear_bytes(coeff, sizeof(coeff));
}

} // namespace

extern "C" {

void dr5_mlkem512_keygen_seed_noise(
    const uint8_t * __restrict req_in,       // 64 bytes (d[32] || z[32])
    const uint8_t * __restrict desc_in,      // 16 bytes
    uint8_t * __restrict tok_out             // 2128 bytes (SecretToken)
) {
    auto *hdr = reinterpret_cast<uint32_t *>(tok_out);
    const uint8_t abi_ver = desc_in[0];
    const uint8_t opcode = desc_in[1];
    const uint8_t param = desc_in[2];
    const uint32_t req_id = *reinterpret_cast<const uint32_t *>(desc_in + 8);
    
    hdr[0] = 0x54434553u; // b"SECT"
    hdr[1] = req_id;
    hdr[2] = 0;
    hdr[3] = 0;
    
    if (abi_ver != 1 || opcode != 0x51 || param != 0x52) {
        hdr[2] = 2; // STATUS_BAD_DESCRIPTOR
        return;
    }
    
    const uint8_t *d = req_in + 0;
    const uint8_t *z = req_in + 32;
    
    // Copy z[32] into secret token
    for (uint32_t i = 0; i < 32; ++i) {
        tok_out[mlkem512_dr5::kZOffset + i] = z[i];
    }
    
    // Compute G(d || 2) -> (rho, sigma) via SHA3-512
    alignas(8) uint8_t state[200];
    mlkem512_dr5::clear_bytes(state, sizeof(state));
    for (uint32_t i = 0; i < 32; ++i) state[i] ^= d[i];
    state[32] ^= 0x02; // k = 2
    state[33] ^= 0x06; // SHA3 domain separation
    state[71] ^= 0x80; // SHA3-512 rate = 72 bytes
    phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
    
    uint8_t *rho = tok_out + mlkem512_dr5::kRhoOffset;
    uint8_t sigma[32];
    for (uint32_t i = 0; i < 32; ++i) {
        rho[i] = state[i];
        sigma[i] = state[32 + i];
    }
    mlkem512_dr5::clear_bytes(state, sizeof(state));
    
    // Sample and transform s0, s1, e0, e1
    sample_cbd3_ntt_store(sigma, 0, tok_out + mlkem512_dr5::kSecretS0Offset);
    sample_cbd3_ntt_store(sigma, 1, tok_out + mlkem512_dr5::kSecretS1Offset);
    sample_cbd3_ntt_store(sigma, 2, tok_out + mlkem512_dr5::kSecretE0Offset);
    sample_cbd3_ntt_store(sigma, 3, tok_out + mlkem512_dr5::kSecretE1Offset);
    
    mlkem512_dr5::clear_bytes(sigma, sizeof(sigma));
}

} // extern "C"
