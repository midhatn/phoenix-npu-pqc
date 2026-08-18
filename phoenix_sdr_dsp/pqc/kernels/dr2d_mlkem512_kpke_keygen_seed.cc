// SPDX-License-Identifier: Apache-2.0
// DR2d worker 0: validate ingress, derive G(d || k), then derive s_hat/e_hat.
// CBD3 and NTT below intentionally match the physically validated DR2b scalar
// formulation: CBD3 fills local uint32 lanes, a noinline NTT transforms those
// lanes, and only then are canonical uint16 values serialized into the FIFO.
#include "dr2d_mlkem512_kpke_keygen_internal.hpp"

namespace {
using namespace phoenix_sdr_dsp::pqc::dr2d;

static uint32_t bit_at(const uint8_t *prf, uint32_t bit) {
  return (prf[bit >> 3] >> (bit & 7)) & 1u;
}

// Exact DR2b CBD3 arithmetic: retain this direct bit extraction rather than
// the fixed-mask packed formulation so the active Phoenix noise path follows
// the already physically validated implementation.
static void cbd3(const uint8_t prf[kPrfBytes], uint32_t out[kN]) {
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t bit = 6 * i;
    const int32_t value = static_cast<int32_t>(bit_at(prf, bit) + bit_at(prf, bit + 1) + bit_at(prf, bit + 2)) - static_cast<int32_t>(bit_at(prf, bit + 3) + bit_at(prf, bit + 4) + bit_at(prf, bit + 5));
    out[i] = static_cast<uint32_t>(value) + (static_cast<uint32_t>(value) >> 31) * kQ;
  }
}

// Exact DR2b noinline uint32 NTT; kZetas is the frozen DR2c/DR2b table.
__attribute__((noinline)) static void ntt(uint32_t r[kN]) {
  uint32_t k = 1;
  DR2D_DISABLE_UNROLL
  for (uint32_t stage = 0; stage < 7; ++stage) {
    const uint32_t length = 128u >> stage;
    DR2D_DISABLE_UNROLL
    for (uint32_t start = 0; start < kN; start += 2 * length) {
      const uint32_t zeta = kZetas[k++];
      DR2D_DISABLE_UNROLL
      for (uint32_t j = start; j < start + length; ++j) {
        const uint32_t t = mod_mul(zeta, r[j + length]);
        r[j + length] = r[j] >= t ? r[j] - t : r[j] + kQ - t;
        const uint32_t sum = r[j] + t;
        r[j] = sum >= kQ ? sum - kQ : sum;
      }
    }
  }
}

static bool cbd3_ntt_store_dr2b(const uint8_t sigma[32], uint8_t counter,
                                 uint8_t out[2 * kN]) {
  if (!word_aligned(out)) return false;
  alignas(8) uint8_t state[200];
  uint8_t prf[kPrfBytes];
  uint32_t coefficients[kN];
  clear_bytes(state, sizeof(state));
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) state[i] ^= sigma[i];
  state[32] ^= counter;
  state[33] ^= 0x1f;
  state[kRate256 - 1] ^= 0x80;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  DR2D_DISABLE_UNROLL
  for (uint32_t i = 0; i < kRate256; ++i) prf[i] = state[i];
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  DR2D_DISABLE_UNROLL
  for (uint32_t i = kRate256; i < kPrfBytes; ++i) prf[i] = state[i - kRate256];
  cbd3(prf, coefficients);
  ntt(coefficients);
  // One aligned 32-bit store per coefficient pair; never a 16-bit store.
  DR2D_DISABLE_UNROLL
  for (uint32_t pair = 0; pair < kN / 2; ++pair)
    store_pair_word(out, pair, coefficients[2 * pair], coefficients[2 * pair + 1]);
  clear_bytes(coefficients, sizeof(coefficients));
  clear_bytes(prf, sizeof(prf));
  clear_bytes(state, sizeof(state));
  return true;
}

static void seed_noise(uint8_t d[32], uint8_t descriptor[16],
                       uint8_t token[kSecretTokenBytes]) {
  const uint32_t id = load_le32(descriptor + 8);
  if (!valid_descriptor(descriptor)) {
    write_header(token, kSecretTokenBytes, id, kBadDescriptor, kSecretHeaderBytes);
  } else if (!word_aligned(token)) {
    // Token base alignment statically justifies every offset store below.
    write_header(token, kSecretTokenBytes, id, kBadToken, kSecretHeaderBytes);
  } else {
    uint8_t rho[32], sigma[32];
    derive_g(d, rho, sigma);
    write_header(token, kSecretTokenBytes, id, kOk, kSecretHeaderBytes);
    // rho is not coefficient storage.  Its 32-byte byte-store loop is exactly
    // the shape the diagnostic probe physically validated on Phoenix, so it is
    // deliberately retained rather than widened by this repair.
    DR2D_DISABLE_UNROLL
    for (uint32_t i = 0; i < 32; ++i) token[kRhoOffset + i] = rho[i];
    const bool stored =
        cbd3_ntt_store_dr2b(sigma, 0, token + kSecretS0Offset) &&
        cbd3_ntt_store_dr2b(sigma, 1, token + kSecretS1Offset) &&
        cbd3_ntt_store_dr2b(sigma, 2, token + kSecretE0Offset) &&
        cbd3_ntt_store_dr2b(sigma, 3, token + kSecretE1Offset);
    clear_bytes(rho, sizeof(rho));
    clear_bytes(sigma, sizeof(sigma));
    if (!stored)
      write_header(token, kSecretTokenBytes, id, kBadToken, kSecretHeaderBytes);
  }
  clear_bytes(d, 32);
  clear_bytes(descriptor, 16);
}
}  // namespace

extern "C" void dr2d_kpke_keygen_seed_noise(uint8_t d[32], uint8_t descriptor[16],
                                             uint8_t token[2096]) {
  seed_noise(d, descriptor, token);
}
