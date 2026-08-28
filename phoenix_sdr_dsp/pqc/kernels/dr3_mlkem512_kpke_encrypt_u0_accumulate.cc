// SPDX-License-Identifier: Apache-2.0
#include "dr3_mlkem512_kpke_encrypt_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr3;

static uint32_t s_acc_u0[kN];

__attribute__((noinline)) static void compute_u0(const uint8_t *col0_token, uint8_t *out_c1_0) {
  ntt_multiply_accumulate(col0_token + kA00Offset, col0_token + kR0Offset,
                          col0_token + kA10Offset, col0_token + kR1Offset,
                          s_acc_u0);
  intt(s_acc_u0);

  const uint8_t *e1_0 = col0_token + kE1_0Offset;
  uint32_t *acc_ptr = s_acc_u0;
  DR3_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t noise = load_le16(e1_0 + 2 * i);
    const uint32_t sum = *acc_ptr + noise;
    *acc_ptr = sum >= kQ ? sum - kQ : sum;
    acc_ptr++;
  }

  compress10_encode(s_acc_u0, out_c1_0);
}

extern "C" void dr3_mlkem512_kpke_encrypt_u0_accumulate(
    const uint8_t col0_token[kCol0TokenBytes],
    uint8_t u0_token[kU0TokenBytes]) {

  if (!word_aligned(col0_token) || !word_aligned(u0_token)) {
    clear_bytes(u0_token, kU0TokenBytes);
    store_le32(u0_token, 0);
    store_le32(u0_token + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(col0_token);
  const uint32_t status = load_le32(col0_token + 4);

  if (status != kOk) {
    clear_bytes(u0_token, kU0TokenBytes);
    store_le32(u0_token, request_id);
    store_le32(u0_token + 4, status);
    return;
  }

  clear_bytes(u0_token, kU0TokenBytes);
  store_le32(u0_token, request_id);
  store_le32(u0_token + 4, kOk);

  // 1. Copy rho (32 B)
  copy_words(u0_token + kU0RhoOffset, col0_token + kRhoOffset, 32);

  // 2. Compute u[0] and store compressed c1_0 (320 B)
  compute_u0(col0_token, u0_token + kU0C1_0Offset);

  // 3. Carry forward needed polynomials for W3/W4:
  copy_words(u0_token + kU0R0Offset, col0_token + kR0Offset, 512);
  copy_words(u0_token + kU0R1Offset, col0_token + kR1Offset, 512);
  copy_words(u0_token + kU0E1_1Offset, col0_token + kE1_1Offset, 512);
  copy_words(u0_token + kU0E2MuOffset, col0_token + kE2MuOffset, 512);
  copy_words(u0_token + kU0T0Offset, col0_token + kT0Offset, 512);
  copy_words(u0_token + kU0T1Offset, col0_token + kT1Offset, 512);
}
