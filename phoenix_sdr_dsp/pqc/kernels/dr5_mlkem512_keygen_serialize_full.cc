// SPDX-License-Identifier: Apache-2.0
#include "dr5_mlkem512_keygen_internal.hpp"
#include <stdint.h>

namespace {

static void encode_12(const uint8_t in[512], uint8_t out[384]) {
    DR5_DISABLE_UNROLL
    for (uint32_t i = 0; i < 128; ++i) {
        const uint32_t c0 = mlkem512_dr5::load_le16(in + 2 * (2 * i + 0)) & 0x0FFFu;
        const uint32_t c1 = mlkem512_dr5::load_le16(in + 2 * (2 * i + 1)) & 0x0FFFu;
        out[3 * i + 0] = static_cast<uint8_t>(c0 & 0xFFu);
        out[3 * i + 1] = static_cast<uint8_t>(((c0 >> 8) & 0x0Fu) | ((c1 & 0x0Fu) << 4));
        out[3 * i + 2] = static_cast<uint8_t>((c1 >> 4) & 0xFFu);
    }
}

} // namespace

extern "C" {

void dr5_mlkem512_keygen_serialize_full(
    const uint8_t * __restrict final_in,     // 2144 bytes (FinalToken)
    uint8_t * __restrict res_out             // 2452 bytes (Result token)
) {
    const auto *in_hdr = reinterpret_cast<const uint32_t *>(final_in);
    auto *res_hdr = reinterpret_cast<uint32_t *>(res_out);
    
    res_hdr[0] = mlkem512_dr5::kResultMagic;
    res_hdr[1] = in_hdr[1]; // request_id
    res_hdr[2] = in_hdr[2]; // status
    res_hdr[3] = 2432u;     // payload bytes (ek[800] + dk[1632])
    res_hdr[4] = 0u;        // crc32
    
    if (in_hdr[0] != 0x54434553u && in_hdr[0] != 0 && in_hdr[2] != 0) {
        return;
    }
    
    uint8_t *ek_ptr = res_out + 20;               // 800 bytes
    uint8_t *dk_ptr = res_out + 20 + 800;         // 1632 bytes
    
    const uint8_t *t0_raw = final_in + mlkem512_dr5::kFinalT0Offset;
    const uint8_t *t1_raw = final_in + mlkem512_dr5::kFinalT1Offset;
    const uint8_t *s0_raw = final_in + mlkem512_dr5::kFinalS0Offset;
    const uint8_t *s1_raw = final_in + mlkem512_dr5::kFinalS1Offset;
    const uint8_t *rho_raw = final_in + mlkem512_dr5::kFinalRhoOffset;
    const uint8_t *z_raw = final_in + mlkem512_dr5::kFinalZOffset;
    
    // 1. Encode ek = ByteEncode12(t0) || ByteEncode12(t1) || rho (800 bytes)
    encode_12(t0_raw, ek_ptr + 0);
    encode_12(t1_raw, ek_ptr + 384);
    for (uint32_t i = 0; i < 32; ++i) {
        ek_ptr[768 + i] = rho_raw[i];
    }
    
    // 2. Encode dk = dk_PKE[768] || ek[800] || H(ek)[32] || z[32] (1632 bytes)
    // 2a. dk_PKE = ByteEncode12(s0) || ByteEncode12(s1) (768 bytes)
    encode_12(s0_raw, dk_ptr + 0);
    encode_12(s1_raw, dk_ptr + 384);
    
    // 2b. ek[800] copied into dk
    for (uint32_t i = 0; i < 800; ++i) {
        dk_ptr[768 + i] = ek_ptr[i];
    }
    
    // 2c. H(ek) = SHA3-256(ek) computed strictly on-chip (32 bytes)
    mlkem512_dr5::sha3_256_800(ek_ptr, dk_ptr + 1568);
    
    // 2d. z[32] copied into dk
    for (uint32_t i = 0; i < 32; ++i) {
        dk_ptr[1600 + i] = z_raw[i];
    }
    
    // 3. Compute CRC32 over the 2432 payload bytes
    const uint32_t crc = mlkem512_dr5::compute_crc32(ek_ptr, 2432);
    res_hdr[4] = crc;
}

} // extern "C"
