// Diagnostic-only predecessor trace for the DR2d W0 ML-KEM-512 noise path.
// It is additive and must never replace or be linked into production KeyGen.
#include <stdint.h>

#include "dr1_keccak_f1600.hpp"

namespace {

constexpr uint32_t kStateBytes = 200u;
constexpr uint32_t kSigmaBytes = 32u;
constexpr uint32_t kPrfBytes = 192u;
constexpr uint32_t kPrfCount = 4u;
constexpr uint32_t kTraceBytes = kSigmaBytes + kPrfCount * kPrfBytes;
constexpr uint32_t kRateG = 72u;
constexpr uint32_t kRateShake256 = 136u;

static inline void clear_bytes(uint8_t *destination, uint32_t bytes) {
  for (uint32_t index = 0; index < bytes; ++index) destination[index] = 0u;
}

// Exact byte staging evidenced for derive_g: SHA3-512(D || 0x02), first 64 bytes.
static inline void derive_sigma(const uint8_t d[kSigmaBytes],
                                uint8_t sigma[kSigmaBytes]) {
  alignas(8) uint8_t state[kStateBytes];
  clear_bytes(state, kStateBytes);
  for (uint32_t index = 0; index < kSigmaBytes; ++index) state[index] ^= d[index];
  state[32] ^= 2u;
  state[33] ^= 0x06u;
  state[kRateG - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t index = 0; index < kSigmaBytes; ++index)
    sigma[index] = state[32u + index];
  clear_bytes(state, kStateBytes);
}

// Exact byte staging evidenced for the W0 SHAKE256 PRF: sigma || nonce,
// SHAKE domain 0x1f at byte 33, pad bit at byte 135, and a 136+56 squeeze.
static inline void shake256_prf_192(const uint8_t sigma[kSigmaBytes],
                                    uint8_t nonce, uint8_t output[kPrfBytes]) {
  alignas(8) uint8_t state[kStateBytes];
  clear_bytes(state, kStateBytes);
  for (uint32_t index = 0; index < kSigmaBytes; ++index)
    state[index] ^= sigma[index];
  state[32] ^= nonce;
  state[33] ^= 0x1fu;
  state[kRateShake256 - 1u] ^= 0x80u;
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t index = 0; index < kRateShake256; ++index)
    output[index] = state[index];
  phoenix_sdr_dsp::pqc::dr1::keccak_f1600(state);
  for (uint32_t index = 0; index < (kPrfBytes - kRateShake256); ++index)
    output[kRateShake256 + index] = state[index];
  clear_bytes(state, kStateBytes);
}

}  // namespace

extern "C" void dr2d_kpke_sigma_prf_tap(
    const uint8_t d[kSigmaBytes], uint8_t trace[kTraceBytes]) {
  uint8_t sigma[kSigmaBytes];
  derive_sigma(d, sigma);
  for (uint32_t index = 0; index < kSigmaBytes; ++index) trace[index] = sigma[index];
  for (uint32_t nonce = 0; nonce < kPrfCount; ++nonce)
    shake256_prf_192(sigma, static_cast<uint8_t>(nonce),
                     trace + kSigmaBytes + nonce * kPrfBytes);
  clear_bytes(sigma, kSigmaBytes);
}
