// SPDX-License-Identifier: Apache-2.0
#include "dr8_mlkem1024_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr8_1024;

// Result layout (4768 B):
// [0..3]: Magic 0x4838524D (b"MR8H")
// [4..7]: request_id
// [8..11]: status
// [12..15]: ek_bytes (1568)
// [16..19]: dk_bytes (3168)
// [20..23]: crc_ek
// [24..27]: crc_dk
// [28..31]: reserved
// [32..1599]: ek (1568 B)
// [1600..4767]: dk (3168 B)
// Total Result Bytes = 4768 B

extern "C" void dr8_mlkem1024_keygen_finalize(
    const uint8_t in_token[4176],
    uint8_t result[4768]) {

  if (!word_aligned(in_token) || !word_aligned(result)) {
    clear_bytes(result, 4768);
    store_le32(result, 0);
    store_le32(result + 4, kBadToken);
    return;
  }

  const uint32_t request_id = load_le32(in_token);
  const uint32_t status = load_le32(in_token + 4);

  if (status != kOk) {
    clear_bytes(result, 4768);
    store_le32(result + 0, 0x4838524Du);
    store_le32(result + 4, request_id);
    store_le32(result + 8, status);
    return;
  }

  const uint8_t *rho = in_token + 16;
  const uint8_t *z = in_token + 48;
  const uint8_t *s0 = in_token + 80;
  const uint8_t *s1 = in_token + 592;
  const uint8_t *s2 = in_token + 1104;
  const uint8_t *s3 = in_token + 1616;
  const uint8_t *t0 = in_token + 2128;
  const uint8_t *t1 = in_token + 2640;
  const uint8_t *t2 = in_token + 3152;
  const uint8_t *t3 = in_token + 3664;

  uint8_t *ek = result + 32;
  uint8_t *dk = result + 1600;

  // 1. Encode ek (1568 B)
  encode_d12(t0, ek + 0);
  encode_d12(t1, ek + 384);
  encode_d12(t2, ek + 768);
  encode_d12(t3, ek + 1152);
  for (uint32_t i = 0; i < 32; ++i) ek[1536 + i] = rho[i];

  // 2. Compute H(ek) = SHA3-256(ek) (32 B)
  uint8_t h_ek[32];
  sha3_256_ek1024(ek, h_ek);

  // 3. Encode dk (3168 B)
  // dk_pke (1536 B)
  encode_d12(s0, dk + 0);
  encode_d12(s1, dk + 384);
  encode_d12(s2, dk + 768);
  encode_d12(s3, dk + 1152);

  // ek (1568 B)
  for (uint32_t i = 0; i < 1568; ++i) dk[1536 + i] = ek[i];

  // H(ek) (32 B)
  for (uint32_t i = 0; i < 32; ++i) dk[3104 + i] = h_ek[i];

  // z (32 B)
  for (uint32_t i = 0; i < 32; ++i) dk[3136 + i] = z[i];

  // 4. Header & CRCs
  store_le32(result + 0, 0x4838524Du);
  store_le32(result + 4, request_id);
  store_le32(result + 8, kOk);
  store_le32(result + 12, 1568);
  store_le32(result + 16, 3168);

  const uint32_t crc_ek = compute_crc32(ek, 1568);
  const uint32_t crc_dk = compute_crc32(dk, 3168);
  store_le32(result + 20, crc_ek);
  store_le32(result + 24, crc_dk);
  store_le32(result + 28, 0);

  clear_bytes(h_ek, sizeof(h_ek));
}
