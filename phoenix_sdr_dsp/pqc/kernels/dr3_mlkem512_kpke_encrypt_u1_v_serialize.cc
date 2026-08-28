// SPDX-License-Identifier: Apache-2.0
#include "dr3_mlkem512_kpke_encrypt_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr3;

constexpr uint32_t kResultMagic = 0x4433524Du; // b"MR3D"

static uint32_t s_acc_u1[kN];

__attribute__((noinline)) static void compute_u1(const uint8_t *col1_token, uint8_t *out_c1_1) {
  ntt_multiply_accumulate(col1_token + kA01Offset, col1_token + kU0R0Offset,
                          col1_token + kA11Offset, col1_token + kU0R1Offset,
                          s_acc_u1);
  intt(s_acc_u1);

  const uint8_t *e1_1 = col1_token + kU0E1_1Offset;
  uint32_t *acc_ptr = s_acc_u1;
  DR3_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t noise = load_le16(e1_1 + 2 * i);
    const uint32_t sum = *acc_ptr + noise;
    *acc_ptr = sum >= kQ ? sum - kQ : sum;
    acc_ptr++;
  }

  compress10_encode(s_acc_u1, out_c1_1);
}

__attribute__((noinline)) static void compute_v(const uint8_t *col1_token, uint8_t *out_c2) {
  ntt_multiply_accumulate(col1_token + kU0T0Offset, col1_token + kU0R0Offset,
                          col1_token + kU0T1Offset, col1_token + kU0R1Offset,
                          s_acc_u1);
  intt(s_acc_u1);

  const uint8_t *e2_mu = col1_token + kU0E2MuOffset;
  uint32_t *acc_ptr = s_acc_u1;
  DR3_DISABLE_UNROLL
  for (uint32_t i = 0; i < kN; ++i) {
    const uint32_t noise_mu = load_le16(e2_mu + 2 * i);
    const uint32_t sum = *acc_ptr + noise_mu;
    *acc_ptr = sum >= kQ ? sum - kQ : sum;
    acc_ptr++;
  }

  compress4_encode(s_acc_u1, out_c2);
}

extern "C" void dr3_mlkem512_kpke_encrypt_u1_v_serialize(
    const uint8_t col1_token[kCol1TokenBytes],
    uint8_t result[kResultBytes]) {

  if (!word_aligned(col1_token) || !word_aligned(result)) {
    clear_bytes(result, kResultBytes);
    store_le32(result, kResultMagic);
    store_le32(result + 4, 0);
    store_le32(result + 8, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(col1_token);
  const uint32_t status = load_le32(col1_token + 4);

  if (status != kOk) {
    clear_bytes(result, kResultBytes);
    store_le32(result, kResultMagic);
    store_le32(result + 4, request_id);
    store_le32(result + 8, status);
    return;
  }

  clear_bytes(result, kResultBytes);

  // 1. Copy c1_0 (320 B) from col1_token to result + 20
  copy_words(result + kResultCiphertextOffset, col1_token + kU0C1_0Offset, 320);

  // 2. Compute u[1] (320 B) at result + 20 + 320
  compute_u1(col1_token, result + kResultCiphertextOffset + 320);

  // 3. Compute v (128 B) at result + 20 + 640
  compute_v(col1_token, result + kResultCiphertextOffset + 640);

  // 4. Compute CRC32 over the 768-byte ciphertext
  uint32_t crc = compute_crc32(result + kResultCiphertextOffset, 768);

  // 5. Commit Header
  store_le32(result, kResultMagic);
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, 768);
  store_le32(result + 16, crc);
}
