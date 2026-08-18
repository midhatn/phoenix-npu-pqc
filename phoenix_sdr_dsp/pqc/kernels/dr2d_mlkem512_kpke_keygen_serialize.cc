// SPDX-License-Identifier: Apache-2.0
// DR2d consumes its private token once, serializes FIPS 203 keys, then clears it.
#include <cstdint>

namespace {
constexpr uint32_t kN = 256, kQ = 3329, kHeaderBytes = 32, kTokenBytes = 2112;
constexpr uint32_t kResultBytes = 1588, kResultHeaderBytes = 20, kEkBytes = 800;
constexpr uint32_t kDkBytes = 768, kOk = 0, kLimitExceeded = 1, kBadDescriptor = 2;
constexpr uint32_t kBadToken = 3;
constexpr uint32_t kResultMagic = 0x4432524D;
static void clear_bytes(void *address, uint32_t bytes) {
  volatile uint8_t *out = static_cast<volatile uint8_t *>(address);
  for (uint32_t i = 0; i < bytes; ++i) out[i] = 0;
}
static uint16_t load_le16(const uint8_t *in) {
  return static_cast<uint16_t>(in[0]) | (static_cast<uint16_t>(in[1]) << 8);
}
static uint32_t load_le32(const uint8_t *in) {
  return static_cast<uint32_t>(in[0]) | (static_cast<uint32_t>(in[1]) << 8) |
         (static_cast<uint32_t>(in[2]) << 16) | (static_cast<uint32_t>(in[3]) << 24);
}
static void store_le16(uint8_t *out, uint16_t x) {
  out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8);
}
static void store_le32(uint8_t *out, uint32_t x) {
  out[0] = static_cast<uint8_t>(x); out[1] = static_cast<uint8_t>(x >> 8);
  out[2] = static_cast<uint8_t>(x >> 16); out[3] = static_cast<uint8_t>(x >> 24);
}
static uint32_t crc32(const uint8_t *data, uint32_t bytes) {
  uint32_t crc = 0xffffffffu;
  for (uint32_t i = 0; i < bytes; ++i) {
    crc ^= data[i];
    for (uint32_t bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}
static bool validate_poly12(const uint8_t *source) {
  for (uint32_t i = 0; i < 128; ++i) {
    const uint32_t a = load_le16(source + 4 * i), b = load_le16(source + 4 * i + 2);
    if (a >= kQ || b >= kQ) return false;
  }
  return true;
}
static void encode_poly12(const uint8_t *source, uint8_t *out) {
  for (uint32_t i = 0; i < 128; ++i) {
    const uint8_t *p = source + 4 * i;
    const uint32_t p0 = p[0], p1 = p[1], p2 = p[2], p3 = p[3];
    out[3 * i] = static_cast<uint8_t>(p0);
    out[3 * i + 1] = static_cast<uint8_t>((p1 & 0x0fu) |
                                            ((p2 & 0x0fu) << 4));
    out[3 * i + 2] = static_cast<uint8_t>(((p2 >> 4) & 0x0fu) |
                                            ((p3 & 0x0fu) << 4));
  }
}
static void write_error(uint8_t result[kResultBytes], uint32_t id, uint32_t status) {
  clear_bytes(result, kResultBytes);
  store_le32(result + 4, id); store_le32(result + 8, status);
  store_le32(result, kResultMagic);  // Commit every terminal record last.
}
static void commit_success(uint8_t result[kResultBytes], uint32_t id) {
  const uint8_t *payload = result + kResultHeaderBytes;
  store_le32(result + 16, crc32(payload, kEkBytes + kDkBytes));
  store_le32(result + 4, id); store_le32(result + 8, kOk);
  store_le16(result + 12, kEkBytes); store_le16(result + 14, kDkBytes);
  store_le32(result, kResultMagic);  // Success magic is the final device store.
}
static void serialize(uint8_t token[kTokenBytes], uint8_t result[kResultBytes]) {
  const uint32_t id = load_le32(token), status = load_le32(token + 4);
  bool reserved = false; for (uint32_t i = 8; i < kHeaderBytes; ++i) reserved |= token[i] != 0;
  if (reserved || (status != kOk && status != kLimitExceeded && status != kBadDescriptor)) {
    write_error(result, id, kBadToken);
  } else if (status != kOk) {
    write_error(result, id, status);
  } else {
    uint8_t *payload = result + kResultHeaderBytes;
    const uint8_t *s0 = token + kHeaderBytes + 32, *s1 = s0 + 512;
    const uint8_t *t0 = s1 + 512, *t1 = t0 + 512;
    clear_bytes(result, kResultBytes);
    if (!validate_poly12(t0) || !validate_poly12(t1) ||
        !validate_poly12(s0) || !validate_poly12(s1)) {
      write_error(result, id, kBadToken);
    } else {
      encode_poly12(t0, payload); encode_poly12(t1, payload + 384);
      encode_poly12(s0, payload + kEkBytes); encode_poly12(s1, payload + kEkBytes + 384);
      for (uint32_t i = 0; i < 32; ++i) payload[768 + i] = token[kHeaderBytes + i];
      commit_success(result, id);
    }
  }
  clear_bytes(token, kTokenBytes);
}
}  // namespace

extern "C" void dr2d_kpke_keygen_serialize(uint8_t token[2112], uint8_t result[1588]) {
  serialize(token, result);
}
