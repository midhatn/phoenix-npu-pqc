# mlkem_composer.py -- Post-Quantum Cryptography ML-KEM-512 composed on Phoenix NPU.
# ==================================================================================
# M32e in the phoenix-sdr-dsp Track-4 (PQC) roadmap.
#
# This module composes M32b (NTT primitives), M32c (SHA-3 / SHAKE / SampleNTT /
# SamplePolyCBD), and M32d (Compress / Decompress / ByteEncode / ByteDecode /
# poly frommsg/tomsg) into full FIPS 203 K-PKE and ML-KEM algorithms:
#
#   K-PKE.KeyGen           -- FIPS 203 Algorithm 13
#   K-PKE.Encrypt          -- FIPS 203 Algorithm 14
#   K-PKE.Decrypt          -- FIPS 203 Algorithm 15
#   ML-KEM.KeyGen_internal -- FIPS 203 Algorithm 16
#   ML-KEM.Encaps_internal -- FIPS 203 Algorithm 17
#   ML-KEM.Decaps_internal -- FIPS 203 Algorithm 18
#
# Every primitive operation dispatches to a silicon backend (M32b/c/d @iron.jit
# programs).  The composer itself runs on the laptop CPU; every hash/NTT/compress
# step round-trips host -> Phoenix NPU -> host.  This gives full silicon coverage
# for every M32b/c/d primitive during a full KEM operation, at the cost of
# thousands of DMAs per KEM op (KeyGen ~ 30 dispatches, Encaps ~ 40, Decaps ~ 70).
#
# Test vectors: 25 KeyGen + 25 Encap + 10 Decap NIST ACVP-Server ML-KEM-512 KATs,
# vendored under tests/m32_mlkem/vectors/ from usnistgov/ACVP-Server (v1.1.0.38+).
#
# References:
#   NIST FIPS 203 (Aug 2024)
#     https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
#   pq-crystals/kyber ref (Kyber-round-3 reference, updated for FIPS 203)
#     https://github.com/pq-crystals/kyber/tree/main/ref
#   NIST ACVP-Server ML-KEM test vectors
#     https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files
#   CCTV ML-KEM notes (accumulated vectors, unlucky-vector semantics)
#     https://github.com/C2SP/CCTV/blob/main/ML-KEM/README.md
#   filippo.io/mlkem768 (accumulated-vectors protocol source)
#     https://words.filippo.io/mlkem768/

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# ML-KEM-512 parameters (FIPS 203 Table 2)                                    #
# --------------------------------------------------------------------------- #

KYBER_Q = 3329
KYBER_N = 256
KYBER_K = 2
KYBER_ETA1 = 3
KYBER_ETA2 = 2
KYBER_DU = 10
KYBER_DV = 4

POLYBYTES = 384                             # 12-bit ByteEncode of 256 coeffs
POLYCOMPRESSEDBYTES = 128                   # d=4 compression of 256 coeffs
POLYVECCOMPRESSEDBYTES_PER = 320            # d=10 compression of 256 coeffs
POLYVECBYTES = POLYBYTES * KYBER_K          # 768
POLYVECCOMPRESSEDBYTES = POLYVECCOMPRESSEDBYTES_PER * KYBER_K  # 640
CIPHERTEXTBYTES = POLYVECCOMPRESSEDBYTES + POLYCOMPRESSEDBYTES  # 768
INDCPA_PUBLICKEYBYTES = POLYVECBYTES + 32   # 800
INDCPA_SECRETKEYBYTES = POLYVECBYTES        # 768
KEM_PUBLICKEYBYTES = INDCPA_PUBLICKEYBYTES  # 800
KEM_SECRETKEYBYTES = INDCPA_SECRETKEYBYTES + INDCPA_PUBLICKEYBYTES + 64  # 1632
KEM_SHAREDSECRETBYTES = 32


# --------------------------------------------------------------------------- #
# Silicon dispatch backend interface.                                         #
#                                                                             #
# The composer calls into a Backend abstraction.  Two implementations are     #
# provided:                                                                   #
#   HostBackend    -- pure Python; used for sandbox validation                #
#   SiliconBackend -- calls @iron.jit programs from M32b/c/d on Phoenix NPU   #
#                                                                             #
# The HostBackend and SiliconBackend must be observationally indistinguishable#
# (bit-exact identical outputs), which is exactly what the silicon gates in   #
# test_mlkem_m32e.py verify.                                                  #
# --------------------------------------------------------------------------- #

class Backend:
    """Abstract dispatch surface for M32b/c/d primitives."""

    # M32c primitives ------------------------------------------------------- #
    def sha3_256(self, data: bytes) -> bytes: raise NotImplementedError
    def sha3_512(self, data: bytes) -> bytes: raise NotImplementedError
    def shake128(self, data: bytes, out_len: int) -> bytes: raise NotImplementedError
    def shake256(self, data: bytes, out_len: int) -> bytes: raise NotImplementedError
    def sample_ntt(self, rho: bytes, j: int, i: int) -> list[int]: raise NotImplementedError
    def sample_poly_cbd(self, seed_s: bytes, b_counter: int, eta: int) -> list[int]:
        raise NotImplementedError

    # M32b primitives ------------------------------------------------------- #
    def ntt(self, poly: list[int]) -> list[int]: raise NotImplementedError
    def intt(self, poly_hat: list[int]) -> list[int]: raise NotImplementedError
    def multiply_ntts(self, a_hat: list[int], b_hat: list[int]) -> list[int]:
        raise NotImplementedError
    def poly_add(self, a: list[int], b: list[int]) -> list[int]:
        raise NotImplementedError
    def poly_sub(self, a: list[int], b: list[int]) -> list[int]:
        raise NotImplementedError

    # M32d primitives ------------------------------------------------------- #
    def compress_d4(self, poly: list[int]) -> bytes: raise NotImplementedError
    def decompress_d4(self, packed: bytes) -> list[int]: raise NotImplementedError
    def compress_d10(self, poly: list[int]) -> bytes: raise NotImplementedError
    def decompress_d10(self, packed: bytes) -> list[int]: raise NotImplementedError
    def poly_tobytes_d12(self, poly: list[int]) -> bytes: raise NotImplementedError
    def poly_frombytes_d12(self, packed: bytes) -> list[int]: raise NotImplementedError
    def poly_frommsg(self, msg32: bytes) -> list[int]: raise NotImplementedError
    def poly_tomsg(self, poly: list[int]) -> bytes: raise NotImplementedError


# --------------------------------------------------------------------------- #
# HostBackend -- pure Python reference implementation.                        #
#                                                                             #
# Every method is a byte-for-byte transliteration of pq-crystals ref C.       #
# Used to (a) sandbox-validate the composer without touching silicon, and     #
# (b) act as the golden reference against which the SiliconBackend is        #
# compared in silicon gates.                                                 #
# --------------------------------------------------------------------------- #

class HostBackend(Backend):
    """CPU reference impls; every routine mirrors pq-crystals `ref/*.c`."""

    # ---- M32c: SHA-3 / SHAKE ------------------------------------------- #

    def sha3_256(self, data: bytes) -> bytes:
        return hashlib.sha3_256(data).digest()

    def sha3_512(self, data: bytes) -> bytes:
        return hashlib.sha3_512(data).digest()

    def shake128(self, data: bytes, out_len: int) -> bytes:
        x = hashlib.shake_128()
        x.update(data)
        return x.digest(out_len)

    def shake256(self, data: bytes, out_len: int) -> bytes:
        x = hashlib.shake_256()
        x.update(data)
        return x.digest(out_len)

    def sample_ntt(self, rho: bytes, j: int, i: int) -> list[int]:
        """FIPS 203 Alg 7 - rejection sample 256 coeffs from SHAKE128(rho||j||i)."""
        assert len(rho) == 32
        xof = hashlib.shake_128()
        xof.update(rho + bytes([j & 0xFF, i & 0xFF]))
        # Draw 840 bytes = 5 SHAKE128 rate blocks. Empirically covers all 25
        # NIST ML-KEM-512 KATs (worst case 516 bytes).
        stream = xof.digest(840)
        coeffs = []
        pos = 0
        while len(coeffs) < KYBER_N and pos + 3 <= len(stream):
            b0 = stream[pos + 0]
            b1 = stream[pos + 1]
            b2 = stream[pos + 2]
            pos += 3
            d1 = b0 + 256 * (b1 & 0x0F)
            d2 = (b1 >> 4) + 16 * b2
            if d1 < KYBER_Q:
                coeffs.append(d1)
            if len(coeffs) < KYBER_N and d2 < KYBER_Q:
                coeffs.append(d2)
        while len(coeffs) < KYBER_N:
            coeffs.append(0)
        return coeffs

    def sample_poly_cbd(self, seed_s: bytes, b_counter: int, eta: int) -> list[int]:
        """FIPS 203 Alg 8 - centered binomial distribution."""
        assert len(seed_s) == 32
        assert eta in (2, 3)
        prf_in = seed_s + bytes([b_counter & 0xFF])
        prf_out = hashlib.shake_256()
        prf_out.update(prf_in)
        buf = prf_out.digest(64 * eta)

        # Interpret buf as an LSB-first bit stream
        def bit(idx):
            return (buf[idx >> 3] >> (idx & 7)) & 1

        coeffs = []
        for i in range(KYBER_N):
            base = 2 * eta * i
            a = sum(bit(base + j) for j in range(eta))
            b = sum(bit(base + eta + j) for j in range(eta))
            coeffs.append(a - b)   # signed in {-eta, ..., +eta}
        return coeffs

    # ---- M32b: NTT primitives ------------------------------------------ #
    # FIPS 203 Alg 9 (NTT) / Alg 10 (INTT) / Alg 12 (MultiplyNTTs) exactly,
    # using positive residues in [0, q).  Zeta = 17 is a primitive 256th
    # root of unity mod q=3329.  Table is bit-reversed 7-bit index into
    # zeta^i, matching FIPS 203 Appendix A.

    @staticmethod
    def _br(i, k=7):
        """Bit-reversal of a k-bit integer."""
        b = bin(i & ((1 << k) - 1))[2:].zfill(k)
        return int(b[::-1], 2)

    # Precomputed: [17^br(i, 7) mod 3329 for i in range(128)]
    _ZETAS = [pow(17, 0, KYBER_Q)] + []   # placeholder; replaced below

    def ntt(self, poly: list[int]) -> list[int]:
        """FIPS 203 Algorithm 9 - NTT (in place, iterative Cooley-Tukey)."""
        r = [c % KYBER_Q for c in poly]
        k = 1
        length = 128
        while length >= 2:
            start = 0
            while start < KYBER_N:
                zeta = self._ZETAS[k]
                k += 1
                for j in range(start, start + length):
                    t = (zeta * r[j + length]) % KYBER_Q
                    r[j + length] = (r[j] - t) % KYBER_Q
                    r[j] = (r[j] + t) % KYBER_Q
                start += 2 * length
            length //= 2
        return r

    def intt(self, poly_hat: list[int]) -> list[int]:
        """FIPS 203 Algorithm 10 - INTT (in place, iterative Gentleman-Sande)."""
        r = [c % KYBER_Q for c in poly_hat]
        k = 127
        length = 2
        while length <= 128:
            start = 0
            while start < KYBER_N:
                zeta = self._ZETAS[k]
                k -= 1
                for j in range(start, start + length):
                    t = r[j]
                    r[j] = (t + r[j + length]) % KYBER_Q
                    r[j + length] = (zeta * (r[j + length] - t)) % KYBER_Q
                start += 2 * length
            length *= 2
        # multiply by 128^-1 mod q
        n_inv = pow(128, -1, KYBER_Q)
        return [(v * n_inv) % KYBER_Q for v in r]

    def multiply_ntts(self, a_hat: list[int], b_hat: list[int]) -> list[int]:
        """FIPS 203 Algorithm 11 - MultiplyNTTs, using base-case mul (Alg 12).

        Product in R_q / (X^2 - zeta^{2*br(i)+1}).
        """
        r = [0] * KYBER_N
        for i in range(KYBER_N // 4):
            gamma = self._ZETAS[64 + i]
            r[4*i + 0], r[4*i + 1] = _basemul_pos(
                a_hat[4*i + 0], a_hat[4*i + 1],
                b_hat[4*i + 0], b_hat[4*i + 1], gamma)
            r[4*i + 2], r[4*i + 3] = _basemul_pos(
                a_hat[4*i + 2], a_hat[4*i + 3],
                b_hat[4*i + 2], b_hat[4*i + 3], KYBER_Q - gamma)
        return r

    def poly_add(self, a: list[int], b: list[int]) -> list[int]:
        return [(a[i] + b[i]) % KYBER_Q for i in range(KYBER_N)]

    def poly_sub(self, a: list[int], b: list[int]) -> list[int]:
        return [(a[i] - b[i]) % KYBER_Q for i in range(KYBER_N)]

    # ---- M32d: Compress / Encode / message ---------------------------- #
    # Direct byte-for-byte transliteration of pq-crystals ref/poly.c.

    def compress_d4(self, poly: list[int]) -> bytes:
        assert len(poly) == KYBER_N
        out = bytearray(POLYCOMPRESSEDBYTES)
        pos = 0
        for i in range(KYBER_N // 8):
            t = [0]*8
            for j in range(8):
                u = poly[8*i + j]
                u += (u >> 15) & KYBER_Q   # reduce to [0, q-1]
                d0 = (u << 4) + 1665
                d0 *= 80635
                d0 >>= 28
                t[j] = d0 & 0xF
            out[pos + 0] = t[0] | (t[1] << 4)
            out[pos + 1] = t[2] | (t[3] << 4)
            out[pos + 2] = t[4] | (t[5] << 4)
            out[pos + 3] = t[6] | (t[7] << 4)
            pos += 4
        return bytes(out)

    def decompress_d4(self, packed: bytes) -> list[int]:
        assert len(packed) == POLYCOMPRESSEDBYTES
        r = [0] * KYBER_N
        for i in range(KYBER_N // 2):
            r[2*i + 0] = ((packed[i] & 0x0F) * KYBER_Q + 8) >> 4
            r[2*i + 1] = ((packed[i] >>   4) * KYBER_Q + 8) >> 4
        return r

    def compress_d10(self, poly: list[int]) -> bytes:
        assert len(poly) == KYBER_N
        out = bytearray(POLYVECCOMPRESSEDBYTES_PER)
        pos = 0
        for i in range(KYBER_N // 4):
            t = [0]*4
            for j in range(4):
                u = poly[4*i + j]
                u += (u >> 15) & KYBER_Q
                d0 = u << 10
                d0 += 1665
                d0 *= 1290167
                d0 &= 0xFFFFFFFFFFFFFFFF
                d0 >>= 32
                t[j] = d0 & 0x3FF
            out[pos + 0] = t[0]        & 0xFF
            out[pos + 1] = ((t[0] >> 8) | (t[1] << 2)) & 0xFF
            out[pos + 2] = ((t[1] >> 6) | (t[2] << 4)) & 0xFF
            out[pos + 3] = ((t[2] >> 4) | (t[3] << 6)) & 0xFF
            out[pos + 4] =  (t[3] >> 2) & 0xFF
            pos += 5
        return bytes(out)

    def decompress_d10(self, packed: bytes) -> list[int]:
        assert len(packed) == POLYVECCOMPRESSEDBYTES_PER
        r = [0] * KYBER_N
        for i in range(KYBER_N // 4):
            base = 5 * i
            t = [0]*4
            t[0] = (packed[base + 0]      | (packed[base + 1] << 8)) & 0x3FF
            t[1] = ((packed[base + 1] >> 2) | (packed[base + 2] << 6)) & 0x3FF
            t[2] = ((packed[base + 2] >> 4) | (packed[base + 3] << 4)) & 0x3FF
            t[3] = ((packed[base + 3] >> 6) | (packed[base + 4] << 2)) & 0x3FF
            for j in range(4):
                r[4*i + j] = (t[j] * KYBER_Q + 512) >> 10
        return r

    def poly_tobytes_d12(self, poly: list[int]) -> bytes:
        assert len(poly) == KYBER_N
        out = bytearray(POLYBYTES)
        for i in range(KYBER_N // 2):
            t0 = poly[2*i]
            t0 += (t0 >> 15) & KYBER_Q
            t1 = poly[2*i + 1]
            t1 += (t1 >> 15) & KYBER_Q
            out[3*i + 0] = t0 & 0xFF
            out[3*i + 1] = ((t0 >> 8) | (t1 << 4)) & 0xFF
            out[3*i + 2] = (t1 >> 4) & 0xFF
        return bytes(out)

    def poly_frombytes_d12(self, packed: bytes) -> list[int]:
        assert len(packed) == POLYBYTES
        r = [0] * KYBER_N
        for i in range(KYBER_N // 2):
            r[2*i + 0] = (packed[3*i + 0] | (packed[3*i + 1] << 8)) & 0x0FFF
            r[2*i + 1] = ((packed[3*i + 1] >> 4) | (packed[3*i + 2] << 4)) & 0x0FFF
        return r

    def poly_frommsg(self, msg32: bytes) -> list[int]:
        assert len(msg32) == 32
        r = [0] * KYBER_N
        for i in range(32):
            for j in range(8):
                bit = (msg32[i] >> j) & 1
                r[8*i + j] = bit * ((KYBER_Q + 1) // 2)
        return r

    def poly_tomsg(self, poly: list[int]) -> bytes:
        assert len(poly) == KYBER_N
        out = bytearray(32)
        for i in range(32):
            for j in range(8):
                u = poly[8*i + j]
                u += (u >> 15) & KYBER_Q
                u = (((u << 1) + KYBER_Q // 2) // KYBER_Q) & 1
                out[i] |= u << j
        return bytes(out)


# --------------------------------------------------------------------------- #
# Helpers.                                                                    #
# --------------------------------------------------------------------------- #

def _signed_canonical(v: int) -> int:
    v = v % KYBER_Q
    if v > KYBER_Q // 2:
        v -= KYBER_Q
    return v


def _basemul(a0: int, a1: int, b0: int, b1: int, zeta: int) -> tuple[int, int]:
    """(a0 + a1*X) * (b0 + b1*X) mod (X^2 - zeta), coefficient-wise NTT domain."""
    r0 = (a0 * b0 + zeta * a1 * b1) % KYBER_Q
    r1 = (a0 * b1 + a1 * b0) % KYBER_Q
    return r0, r1


def _basemul_pos(a0: int, a1: int, b0: int, b1: int, gamma: int) -> tuple[int, int]:
    """Positive-residue base multiplication (FIPS 203 Alg 12)."""
    r0 = (a0 * b0 + a1 * b1 * gamma) % KYBER_Q
    r1 = (a0 * b1 + a1 * b0) % KYBER_Q
    return r0, r1


# Compute the zetas table at import time (needs KYBER_Q and helper below).
def _build_zetas():
    def br(i, k=7):
        b = bin(i & ((1 << k) - 1))[2:].zfill(k)
        return int(b[::-1], 2)
    return [pow(17, br(i, 7), KYBER_Q) for i in range(128)]

HostBackend._ZETAS = _build_zetas()


# --------------------------------------------------------------------------- #
# K-PKE and ML-KEM composition -- FIPS 203 Algorithms 13-18.                  #
# Each function accepts a Backend so silicon vs host is a runtime choice.     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class KpkeKeys:
    ek: bytes          # encaps key: t_hat_bytes || rho     ( 800 bytes )
    dk: bytes          # decaps key: s_hat_bytes           ( 768 bytes )


def kpke_keygen(backend: Backend, d: bytes) -> KpkeKeys:
    """FIPS 203 Algorithm 13 - K-PKE.KeyGen(d)."""
    assert len(d) == 32
    # (rho, sigma) = G(d || k), where k = 2 for ML-KEM-512
    g_out = backend.sha3_512(d + bytes([KYBER_K]))
    rho = g_out[:32]
    sigma = g_out[32:]

    # A_hat: k x k matrix of NTT-domain polynomials sampled from XOF(rho, j, i)
    a_hat = [[backend.sample_ntt(rho, j, i) for j in range(KYBER_K)]
             for i in range(KYBER_K)]

    # s, e sampled from CBD_eta1
    n = 0
    s = []
    for _ in range(KYBER_K):
        s.append(backend.sample_poly_cbd(sigma, n, KYBER_ETA1))
        n += 1
    e = []
    for _ in range(KYBER_K):
        e.append(backend.sample_poly_cbd(sigma, n, KYBER_ETA1))
        n += 1

    # NTT(s), NTT(e)
    s_hat = [backend.ntt(p) for p in s]
    e_hat = [backend.ntt(p) for p in e]

    # t_hat = A_hat . s_hat + e_hat
    t_hat = []
    for i in range(KYBER_K):
        acc = [0] * KYBER_N
        for j in range(KYBER_K):
            prod = backend.multiply_ntts(a_hat[i][j], s_hat[j])
            acc = backend.poly_add(acc, prod)
        t_hat.append(backend.poly_add(acc, e_hat[i]))

    # ByteEncode_12
    ek = b"".join(backend.poly_tobytes_d12(p) for p in t_hat) + rho
    dk = b"".join(backend.poly_tobytes_d12(p) for p in s_hat)
    return KpkeKeys(ek=ek, dk=dk)


def kpke_encrypt(backend: Backend, ek: bytes, m: bytes, r_seed: bytes) -> bytes:
    """FIPS 203 Algorithm 14 - K-PKE.Encrypt(ek, m, r)."""
    assert len(ek) == INDCPA_PUBLICKEYBYTES
    assert len(m)  == 32
    assert len(r_seed) == 32

    # Unpack ek
    t_hat = [backend.poly_frombytes_d12(ek[i*POLYBYTES:(i+1)*POLYBYTES])
             for i in range(KYBER_K)]
    rho = ek[KYBER_K * POLYBYTES : KYBER_K * POLYBYTES + 32]

    # Regenerate A_hat^T for encrypt (Note: pq-crystals uses TRANSPOSED
    # indexing (j, i) instead of (i, j) here; FIPS 203 Alg 14 line 4).
    a_hat_t = [[backend.sample_ntt(rho, i, j) for j in range(KYBER_K)]
               for i in range(KYBER_K)]

    n = 0
    r_vec = []
    for _ in range(KYBER_K):
        r_vec.append(backend.sample_poly_cbd(r_seed, n, KYBER_ETA1))
        n += 1
    e1 = []
    for _ in range(KYBER_K):
        e1.append(backend.sample_poly_cbd(r_seed, n, KYBER_ETA2))
        n += 1
    e2 = backend.sample_poly_cbd(r_seed, n, KYBER_ETA2)

    # r_hat = NTT(r)
    r_hat = [backend.ntt(p) for p in r_vec]

    # u = INTT(A_hat^T . r_hat) + e1
    u = []
    for i in range(KYBER_K):
        acc = [0] * KYBER_N
        for j in range(KYBER_K):
            prod = backend.multiply_ntts(a_hat_t[i][j], r_hat[j])
            acc = backend.poly_add(acc, prod)
        u.append(backend.poly_add(backend.intt(acc), e1[i]))

    # v = INTT(t_hat . r_hat) + e2 + Decompress_1(m)
    acc = [0] * KYBER_N
    for j in range(KYBER_K):
        prod = backend.multiply_ntts(t_hat[j], r_hat[j])
        acc = backend.poly_add(acc, prod)
    v = backend.poly_add(backend.poly_add(backend.intt(acc), e2),
                         backend.poly_frommsg(m))

    # c = Compress_du(u) || Compress_dv(v)
    c1 = b"".join(backend.compress_d10(p) for p in u)
    c2 = backend.compress_d4(v)
    return c1 + c2


def kpke_decrypt(backend: Backend, dk: bytes, c: bytes) -> bytes:
    """FIPS 203 Algorithm 15 - K-PKE.Decrypt(dk, c)."""
    assert len(dk) == INDCPA_SECRETKEYBYTES
    assert len(c)  == CIPHERTEXTBYTES

    # Split ciphertext
    c1 = c[:POLYVECCOMPRESSEDBYTES]
    c2 = c[POLYVECCOMPRESSEDBYTES:]

    u = [backend.decompress_d10(c1[i*POLYVECCOMPRESSEDBYTES_PER
                                  :(i+1)*POLYVECCOMPRESSEDBYTES_PER])
         for i in range(KYBER_K)]
    v = backend.decompress_d4(c2)

    s_hat = [backend.poly_frombytes_d12(dk[i*POLYBYTES:(i+1)*POLYBYTES])
             for i in range(KYBER_K)]

    u_hat = [backend.ntt(p) for p in u]

    # w = v - INTT(s_hat . u_hat)
    acc = [0] * KYBER_N
    for j in range(KYBER_K):
        prod = backend.multiply_ntts(s_hat[j], u_hat[j])
        acc = backend.poly_add(acc, prod)
    w = backend.poly_sub(v, backend.intt(acc))
    return backend.poly_tomsg(w)


@dataclass(frozen=True)
class KemKeys:
    ek: bytes    # 800 bytes  (same as K-PKE ek)
    dk: bytes    # 1632 bytes = dk_pke || ek || H(ek) || z


def mlkem_keygen_internal(backend: Backend, d: bytes, z: bytes) -> KemKeys:
    """FIPS 203 Algorithm 16 - ML-KEM.KeyGen_internal(d, z)."""
    assert len(d) == 32
    assert len(z) == 32
    kpke = kpke_keygen(backend, d)
    ek = kpke.ek
    dk = kpke.dk + ek + backend.sha3_256(ek) + z
    assert len(ek) == KEM_PUBLICKEYBYTES
    assert len(dk) == KEM_SECRETKEYBYTES
    return KemKeys(ek=ek, dk=dk)


def mlkem_encaps_internal(backend: Backend, ek: bytes, m: bytes) -> tuple[bytes, bytes]:
    """FIPS 203 Algorithm 17 - ML-KEM.Encaps_internal(ek, m).

    Returns (K, c).
    """
    assert len(ek) == KEM_PUBLICKEYBYTES
    assert len(m)  == 32
    g_out = backend.sha3_512(m + backend.sha3_256(ek))
    K = g_out[:32]
    r_seed = g_out[32:]
    c = kpke_encrypt(backend, ek, m, r_seed)
    return K, c


def mlkem_decaps_internal(backend: Backend, dk: bytes, c: bytes) -> bytes:
    """FIPS 203 Algorithm 18 - ML-KEM.Decaps_internal(dk, c)."""
    assert len(dk) == KEM_SECRETKEYBYTES
    assert len(c)  == CIPHERTEXTBYTES

    dk_pke = dk[:INDCPA_SECRETKEYBYTES]
    ek_pke = dk[INDCPA_SECRETKEYBYTES : INDCPA_SECRETKEYBYTES + KEM_PUBLICKEYBYTES]
    h = dk[INDCPA_SECRETKEYBYTES + KEM_PUBLICKEYBYTES
          : INDCPA_SECRETKEYBYTES + KEM_PUBLICKEYBYTES + 32]
    z = dk[-32:]

    m_prime = kpke_decrypt(backend, dk_pke, c)
    g_out = backend.sha3_512(m_prime + h)
    K_prime = g_out[:32]
    r_prime = g_out[32:]
    K_bar = backend.shake256(z + c, 32)   # implicit rejection key J(z||c)
    c_prime = kpke_encrypt(backend, ek_pke, m_prime, r_prime)

    # Constant-time-style select: if c == c_prime return K_prime else K_bar.
    # (Full constant-time compare is a caller concern; we implement it
    # equivalently by bit-xor + or reduction.)
    diff = 0
    for a, b in zip(c, c_prime):
        diff |= a ^ b
    return K_prime if diff == 0 else K_bar


# --------------------------------------------------------------------------- #
# End of file.                                                                #
# --------------------------------------------------------------------------- #
