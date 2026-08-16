// SPDX-License-Identifier: MIT
// M32d — K-PKE byte-serialization + compression primitives on AIE2
//
// Post-Quantum Cryptography (PQC) — FIPS 203 (ML-KEM) support layer.
//
// This single-tile kernel implements the byte-level Compress/Decompress and
// ByteEncode/ByteDecode primitives that FIPS 203 Algorithms 13-15
// (K-PKE.KeyGen / K-PKE.Encrypt / K-PKE.Decrypt) call around every polynomial.
// Combined with M32b (NTT/INTT/MultiplyNTTs/BaseCaseMultiply, poly add/sub)
// and M32c (SHA-3, SHAKE, SampleNTT, SamplePolyCBD) it closes the compute
// floor needed to compose ML-KEM-512 (M32e).
//
// Every routine is a line-for-line transliteration of the pq-crystals
// reference implementation:
//   ref/poly.c poly_compress   / poly_decompress   (d=4,  KYBER_POLYCOMPRESSEDBYTES=128)
//   ref/poly.c poly_tobytes    / poly_frombytes    (d=12, KYBER_POLYBYTES=384)
//   ref/poly.c poly_frommsg    / poly_tomsg        (d=1,  KYBER_INDCPA_MSGBYTES=32)
//   ref/polyvec.c polyvec_compress / polyvec_decompress (d=10, per-poly slice = 320B)
//
// References
//   NIST FIPS 203, August 2024:
//     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
//   pq-crystals/kyber ref:
//     https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
//     https://github.com/pq-crystals/kyber/blob/main/ref/polyvec.c
//     https://github.com/pq-crystals/kyber/blob/main/ref/params.h
//
// AIE2 style (M22..M32c lineage):
//   - NOCPP, no libc <math.h>
//   - int16 buffers; byte streams are packed as low byte of int16 lanes
//   - 2 in-fifos + 1 out-fifo topology (M27 lesson)
//   - every counted loop carries #pragma clang loop unroll(disable) to fit
//     the 16 KiB program-memory budget
//   - static helpers marked __attribute__((noinline))

#include <stdint.h>

extern "C" {

// FIPS 203 ring parameters (verbatim from pq-crystals/kyber/ref/params.h).
static const int16_t KYBER_Q = 3329;
static const int16_t KYBER_N = 256;

// Buffer sizes (bytes of on-tile buffer measured in int16 lanes, since each
// byte occupies one int16 lane). Sized for the largest mode we support:
//   d=10 needs 320 output bytes; d=12 needs 384 output bytes -> 512 lanes
//   is the safe cover for both input and output.
static const int MAX_LANES = 512;
static const int CTRL_LEN  = 8;

// Modes
static const int16_t MODE_COMPRESS_D4     = 0; // poly_compress   (d=4)  256 int16 -> 128 uint8
static const int16_t MODE_DECOMPRESS_D4   = 1; // poly_decompress (d=4)  128 uint8 -> 256 int16
static const int16_t MODE_COMPRESS_D10    = 2; // polyvec_compress one poly (d=10) 256 int16 -> 320 uint8
static const int16_t MODE_DECOMPRESS_D10  = 3; // polyvec_decompress one poly (d=10) 320 uint8 -> 256 int16
static const int16_t MODE_TOBYTES_D12     = 4; // poly_tobytes   (d=12)  256 int16 -> 384 uint8
static const int16_t MODE_FROMBYTES_D12   = 5; // poly_frombytes (d=12)  384 uint8 -> 256 int16
static const int16_t MODE_FROMMSG         = 6; // poly_frommsg    32 uint8 -> 256 int16
static const int16_t MODE_TOMSG           = 7; // poly_tomsg     256 int16 -> 32 uint8

// ---------- helpers ----------

// Signed-to-positive canonical representative (pq-crystals idiom):
//   u += (u >> 15) & KYBER_Q
// yields u in [0, q-1] whenever the caller has already Barrett-reduced.
static inline __attribute__((always_inline)) uint16_t
canonical(int16_t v) {
  int16_t s = (int16_t)((int16_t)(v >> 15) & KYBER_Q);
  int16_t r = (int16_t)(v + s);
  return (uint16_t)r;
}

// Pack a uint8 into the low byte of an int16 lane; high byte cleared.
static inline __attribute__((always_inline)) int16_t
pack_byte(uint8_t b) {
  return (int16_t)((uint16_t)b);
}

// Extract low byte from int16 lane (unsigned, 0..255).
static inline __attribute__((always_inline)) uint8_t
unpack_byte(int16_t lane) {
  return (uint8_t)((uint16_t)lane & 0xFFu);
}

// ---------- poly_compress d=4 (KYBER_POLYCOMPRESSEDBYTES == 128) ----------
// Line-for-line pq-crystals ref/poly.c lines 26-46.
static void __attribute__((noinline))
kernel_compress_d4(const int16_t* in_coeffs, int16_t* out_bytes) {
  uint8_t t[8];
  int r_ofs = 0;

  #pragma clang loop unroll(disable)
  for (int i = 0; i < 256 / 8; i++) {
    #pragma clang loop unroll(disable)
    for (int j = 0; j < 8; j++) {
      int16_t u = in_coeffs[8 * i + j];
      u = (int16_t)(u + (int16_t)((u >> 15) & KYBER_Q));
      uint32_t d0 = (uint32_t)((uint16_t)u) << 4;
      d0 += 1665u;
      d0 *= 80635u;
      d0 >>= 28;
      t[j] = (uint8_t)(d0 & 0xFu);
    }
    out_bytes[r_ofs + 0] = pack_byte((uint8_t)(t[0] | (t[1] << 4)));
    out_bytes[r_ofs + 1] = pack_byte((uint8_t)(t[2] | (t[3] << 4)));
    out_bytes[r_ofs + 2] = pack_byte((uint8_t)(t[4] | (t[5] << 4)));
    out_bytes[r_ofs + 3] = pack_byte((uint8_t)(t[6] | (t[7] << 4)));
    r_ofs += 4;
  }
}

// ---------- poly_decompress d=4 (KYBER_POLYCOMPRESSEDBYTES == 128) ----------
// Line-for-line pq-crystals ref/poly.c lines 87-92.
static void __attribute__((noinline))
kernel_decompress_d4(const int16_t* in_bytes, int16_t* out_coeffs) {
  #pragma clang loop unroll(disable)
  for (int i = 0; i < 256 / 2; i++) {
    uint8_t a0 = unpack_byte(in_bytes[i]);
    uint16_t lo = (uint16_t)(a0 & 15u);
    uint16_t hi = (uint16_t)(a0 >> 4);
    out_coeffs[2 * i + 0] = (int16_t)(((uint16_t)(lo * (uint16_t)KYBER_Q) + 8u) >> 4);
    out_coeffs[2 * i + 1] = (int16_t)(((uint16_t)(hi * (uint16_t)KYBER_Q) + 8u) >> 4);
  }
}

// ---------- polyvec_compress d=10 (single poly slice, 320 bytes) ----------
// Line-for-line pq-crystals ref/polyvec.c lines 50-73 (KYBER_K=2 branch,
// per-poly stride 320 bytes = 5 bytes per 4 coefficients).
static void __attribute__((noinline))
kernel_compress_d10(const int16_t* in_coeffs, int16_t* out_bytes) {
  uint16_t t[4];
  int r_ofs = 0;

  #pragma clang loop unroll(disable)
  for (int j = 0; j < 256 / 4; j++) {
    #pragma clang loop unroll(disable)
    for (int k = 0; k < 4; k++) {
      int16_t v = in_coeffs[4 * j + k];
      uint16_t tk = (uint16_t)v;
      tk = (uint16_t)((int16_t)tk + (int16_t)((int16_t)(((int16_t)tk) >> 15) & KYBER_Q));
      uint64_t d0 = (uint64_t)tk;
      d0 <<= 10;
      d0 += 1665ull;
      d0 *= 1290167ull;
      d0 >>= 32;
      t[k] = (uint16_t)(d0 & 0x3FFu);
    }
    out_bytes[r_ofs + 0] = pack_byte((uint8_t)(t[0] >> 0));
    out_bytes[r_ofs + 1] = pack_byte((uint8_t)((t[0] >> 8) | (t[1] << 2)));
    out_bytes[r_ofs + 2] = pack_byte((uint8_t)((t[1] >> 6) | (t[2] << 4)));
    out_bytes[r_ofs + 3] = pack_byte((uint8_t)((t[2] >> 4) | (t[3] << 6)));
    out_bytes[r_ofs + 4] = pack_byte((uint8_t)(t[3] >> 2));
    r_ofs += 5;
  }
}

// ---------- polyvec_decompress d=10 (single poly slice, 320 bytes) ----------
// Line-for-line pq-crystals ref/polyvec.c lines 111-124.
static void __attribute__((noinline))
kernel_decompress_d10(const int16_t* in_bytes, int16_t* out_coeffs) {
  uint16_t t[4];
  int a_ofs = 0;

  #pragma clang loop unroll(disable)
  for (int j = 0; j < 256 / 4; j++) {
    uint16_t a0 = (uint16_t)unpack_byte(in_bytes[a_ofs + 0]);
    uint16_t a1 = (uint16_t)unpack_byte(in_bytes[a_ofs + 1]);
    uint16_t a2 = (uint16_t)unpack_byte(in_bytes[a_ofs + 2]);
    uint16_t a3 = (uint16_t)unpack_byte(in_bytes[a_ofs + 3]);
    uint16_t a4 = (uint16_t)unpack_byte(in_bytes[a_ofs + 4]);
    t[0] = (uint16_t)((a0 >> 0) | (a1 << 8));
    t[1] = (uint16_t)((a1 >> 2) | (a2 << 6));
    t[2] = (uint16_t)((a2 >> 4) | (a3 << 4));
    t[3] = (uint16_t)((a3 >> 6) | (a4 << 2));
    a_ofs += 5;

    #pragma clang loop unroll(disable)
    for (int k = 0; k < 4; k++) {
      uint32_t x = (uint32_t)(t[k] & 0x3FFu) * (uint32_t)((uint16_t)KYBER_Q) + 512u;
      out_coeffs[4 * j + k] = (int16_t)(x >> 10);
    }
  }
}

// ---------- poly_tobytes d=12 (KYBER_POLYBYTES == 384) ----------
// Line-for-line pq-crystals ref/poly.c lines 124-139.
static void __attribute__((noinline))
kernel_tobytes_d12(const int16_t* in_coeffs, int16_t* out_bytes) {
  #pragma clang loop unroll(disable)
  for (int i = 0; i < 256 / 2; i++) {
    int16_t c0 = in_coeffs[2 * i + 0];
    int16_t c1 = in_coeffs[2 * i + 1];
    uint16_t t0 = (uint16_t)c0;
    t0 = (uint16_t)((int16_t)t0 + (int16_t)(((int16_t)t0 >> 15) & KYBER_Q));
    uint16_t t1 = (uint16_t)c1;
    t1 = (uint16_t)((int16_t)t1 + (int16_t)(((int16_t)t1 >> 15) & KYBER_Q));
    out_bytes[3 * i + 0] = pack_byte((uint8_t)(t0 >> 0));
    out_bytes[3 * i + 1] = pack_byte((uint8_t)((t0 >> 8) | (t1 << 4)));
    out_bytes[3 * i + 2] = pack_byte((uint8_t)(t1 >> 4));
  }
}

// ---------- poly_frombytes d=12 (KYBER_POLYBYTES == 384) ----------
// Line-for-line pq-crystals ref/poly.c lines 151-158.
static void __attribute__((noinline))
kernel_frombytes_d12(const int16_t* in_bytes, int16_t* out_coeffs) {
  #pragma clang loop unroll(disable)
  for (int i = 0; i < 256 / 2; i++) {
    uint16_t b0 = (uint16_t)unpack_byte(in_bytes[3 * i + 0]);
    uint16_t b1 = (uint16_t)unpack_byte(in_bytes[3 * i + 1]);
    uint16_t b2 = (uint16_t)unpack_byte(in_bytes[3 * i + 2]);
    out_coeffs[2 * i + 0] = (int16_t)(((b0 >> 0) | (b1 << 8)) & 0xFFFu);
    out_coeffs[2 * i + 1] = (int16_t)(((b1 >> 4) | (b2 << 4)) & 0xFFFu);
  }
}

// ---------- poly_frommsg (32-byte message -> 256-coeff poly) ----------
// pq-crystals ref/poly.c lines 168-182. We open-code the constant-time
// cmov here since AIE has no cmov intrinsic; branch is on a public bit
// derived from the ciphertext-message plaintext, which is public at this
// layer of M32d (we do not defend against timing attacks in this milestone,
// only bit-exactness against the reference).
static void __attribute__((noinline))
kernel_frommsg(const int16_t* in_bytes, int16_t* out_coeffs) {
  const int16_t mask = (int16_t)((KYBER_Q + 1) / 2);
  #pragma clang loop unroll(disable)
  for (int i = 0; i < 32; i++) {
    uint8_t mi = unpack_byte(in_bytes[i]);
    #pragma clang loop unroll(disable)
    for (int j = 0; j < 8; j++) {
      int16_t bit = (int16_t)((mi >> j) & 1u);
      // constant-time-style: coeff = bit * mask  (0 or (q+1)/2)
      out_coeffs[8 * i + j] = (int16_t)(bit * mask);
    }
  }
}

// ---------- poly_tomsg (256-coeff poly -> 32-byte message) ----------
// pq-crystals ref/poly.c lines 192-211.
static void __attribute__((noinline))
kernel_tomsg(const int16_t* in_coeffs, int16_t* out_bytes) {
  #pragma clang loop unroll(disable)
  for (int i = 0; i < 32; i++) {
    uint8_t mi = 0u;
    #pragma clang loop unroll(disable)
    for (int j = 0; j < 8; j++) {
      // t starts as the coefficient reinterpreted as uint32.
      // The pq-crystals code writes:
      //     t  = a->coeffs[8*i+j];
      //     t <<= 1;
      //     t += 1665;
      //     t *= 80635;
      //     t >>= 28;
      //     t &= 1;
      // On the reference host `a->coeffs` is int16 which sign-extends into
      // uint32. But pq-crystals never calls poly_tomsg on a signed poly;
      // callers Barrett-reduce first (see indcpa_dec). We follow that
      // contract and canonicalize here to be safe and bit-exact with the
      // Barrett-reduced expectation.
      int16_t v = in_coeffs[8 * i + j];
      v = (int16_t)(v + (int16_t)((v >> 15) & KYBER_Q));
      uint32_t t = (uint32_t)((uint16_t)v);
      t <<= 1;
      t += 1665u;
      t *= 80635u;
      t >>= 28;
      t &= 1u;
      mi = (uint8_t)(mi | (uint8_t)(t << j));
    }
    out_bytes[i] = pack_byte(mi);
  }
}

// ---------- entrypoint ----------
// Fifo topology (M32c/M32b lesson): 2 in-fifos, 1 out-fifo.
//   in_a[MAX_LANES]  : input data (either 256 int16 coeffs OR up to 384 packed bytes)
//   in_ctrl[CTRL_LEN]: {mode, ...}
//   out_c[MAX_LANES] : output data (opposite type of in_a)
void kpke(int16_t* __restrict in_a,
          int16_t* __restrict in_ctrl,
          int16_t* __restrict out_c) {
  int16_t mode = in_ctrl[0];

  // Zero the tail of the output buffer so unused lanes are deterministic.
  #pragma clang loop unroll(disable)
  for (int k = 0; k < MAX_LANES; k++) out_c[k] = 0;

  if (mode == MODE_COMPRESS_D4) {
    kernel_compress_d4(in_a, out_c);
  } else if (mode == MODE_DECOMPRESS_D4) {
    kernel_decompress_d4(in_a, out_c);
  } else if (mode == MODE_COMPRESS_D10) {
    kernel_compress_d10(in_a, out_c);
  } else if (mode == MODE_DECOMPRESS_D10) {
    kernel_decompress_d10(in_a, out_c);
  } else if (mode == MODE_TOBYTES_D12) {
    kernel_tobytes_d12(in_a, out_c);
  } else if (mode == MODE_FROMBYTES_D12) {
    kernel_frombytes_d12(in_a, out_c);
  } else if (mode == MODE_FROMMSG) {
    kernel_frommsg(in_a, out_c);
  } else if (mode == MODE_TOMSG) {
    kernel_tomsg(in_a, out_c);
  }
}

} // extern "C"
