// SPDX-License-Identifier: Apache-2.0
// DR12 Worker 3: MakeHint, pack signature, seal with CRC32.
// Stack-optimised: reads z, w_minus_cs2, c_t0 directly from in_token via load_le32.
#include "dr12_mldsa44_sign_internal.hpp"

using namespace phoenix_sdr_dsp::pqc::dr11;
using namespace phoenix_sdr_dsp::pqc::dr12;

extern "C" void dr12_mldsa44_sign_w3_hints_seal(
    const uint8_t in_token[12328],
    uint8_t result[2444]) {

  clear_bytes(result, 2444);

  const uint32_t request_id = load_le32(in_token + 0);
  const uint8_t *c_tilde = in_token + 4; // 32 B

  // Token layout:
  // [36..4131]    z[4][256]          (4096 B)
  // [4132..8227]  w_minus_cs2[4][256] (4096 B)
  // [8228..12323] c_t0[4][256]       (4096 B)

  // 1. MakeHint(-c*t0, w - c*s2 + c*t0) — read directly from in_token
  int32_t h[4][256];
  for (uint32_t i = 0; i < 4; ++i) {
    const uint8_t *wcs2_src = in_token + 4132 + i * 1024;
    const uint8_t *ct0_src  = in_token + 8228 + i * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      const int32_t ct0_val = static_cast<int32_t>(load_le32(ct0_src + c * 4));
      const int32_t wcs2_val = static_cast<int32_t>(load_le32(wcs2_src + c * 4));
      const int32_t neg_ct0 = canonicalize(-ct0_val);
      const int32_t r_plus_ct0 = canonicalize(wcs2_val + ct0_val);
      h[i][c] = make_hint(neg_ct0, r_plus_ct0);
    }
  }

  // 2. Pack Signature: c_tilde[32] || zEncode(z)[2304] || hintEncode(h)[84] = 2420 B
  uint8_t *sig = result + 20;

  // c_tilde (32 B)
  DR11_DISABLE_UNROLL
  for (uint32_t i = 0; i < 32; ++i) sig[i] = c_tilde[i];

  // z encode: read each z poly from in_token, encode to sig
  int32_t poly[256];
  for (uint32_t j = 0; j < 4; ++j) {
    const uint8_t *z_src = in_token + 36 + j * 1024;
    DR11_DISABLE_UNROLL
    for (uint32_t c = 0; c < 256; ++c) {
      poly[c] = static_cast<int32_t>(load_le32(z_src + c * 4));
    }
    encode_z_poly(poly, sig + 32 + j * 576);
  }

  // h (84 B)
  encode_hints(h, sig + 2336);

  // 3. Pack Header & Hardware CRC32
  store_le32(result + 0, 0x4432524Du); // b"MR2D"
  store_le32(result + 4, request_id);
  store_le32(result + 8, 0);           // Status OK
  store_le32(result + 12, 2420);       // Sig bytes

  const uint32_t crc = compute_crc32(result + 20, 2420);
  store_le32(result + 16, crc);

  clear_bytes(h, sizeof(h));
  clear_bytes(poly, sizeof(poly));
}
