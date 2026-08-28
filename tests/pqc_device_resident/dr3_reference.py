"""Independent pure-Python reference oracle for ML-KEM-512 K-PKE.Encrypt (FIPS 203 Algorithm 14)."""

from __future__ import annotations

import hashlib

Q = 3329
N = 256
K = 2
ETA1 = 3
ETA2 = 2
DU = 10
DV = 4


def _build_zetas() -> list[int]:
    def br(i: int, k: int = 7) -> int:
        b = bin(i & ((1 << k) - 1))[2:].zfill(k)
        return int(b[::-1], 2)
    return [pow(17, br(i, 7), Q) for i in range(128)]


ZETAS = _build_zetas()


def byte_decode_12(packed: bytes) -> list[int]:
    """Decode 384 bytes into 256 coefficients."""
    r = [0] * N
    for i in range(N // 2):
        r[2 * i + 0] = (packed[3 * i + 0] | (packed[3 * i + 1] << 8)) & 0x0FFF
        r[2 * i + 1] = ((packed[3 * i + 1] >> 4) | (packed[3 * i + 2] << 4)) & 0x0FFF
    return r


def ntt(poly: list[int]) -> list[int]:
    """FIPS 203 Algorithm 9 - NTT."""
    r = [c % Q for c in poly]
    k = 1
    length = 128
    while length >= 2:
        start = 0
        while start < N:
            zeta = ZETAS[k]
            k += 1
            for j in range(start, start + length):
                t = (zeta * r[j + length]) % Q
                r[j + length] = (r[j] - t) % Q
                r[j] = (r[j] + t) % Q
            start += 2 * length
        length //= 2
    return r


def intt(poly_hat: list[int]) -> list[int]:
    """FIPS 203 Algorithm 10 - INTT."""
    r = [c % Q for c in poly_hat]
    k = 127
    length = 2
    while length <= 128:
        start = 0
        while start < N:
            zeta = ZETAS[k]
            k -= 1
            for j in range(start, start + length):
                t = r[j]
                r[j] = (t + r[j + length]) % Q
                r[j + length] = (zeta * (r[j + length] - t)) % Q
            start += 2 * length
        length *= 2
    n_inv = pow(128, -1, Q)
    return [(v * n_inv) % Q for v in r]


def _basemul_pos(a0: int, a1: int, b0: int, b1: int, gamma: int) -> tuple[int, int]:
    r0 = (a0 * b0 + a1 * b1 * gamma) % Q
    r1 = (a0 * b1 + a1 * b0) % Q
    return r0, r1


def multiply_ntts(a_hat: list[int], b_hat: list[int]) -> list[int]:
    """FIPS 203 Algorithm 11 - MultiplyNTTs."""
    r = [0] * N
    for i in range(N // 4):
        gamma = ZETAS[64 + i]
        r[4 * i + 0], r[4 * i + 1] = _basemul_pos(
            a_hat[4 * i + 0], a_hat[4 * i + 1],
            b_hat[4 * i + 0], b_hat[4 * i + 1], gamma
        )
        r[4 * i + 2], r[4 * i + 3] = _basemul_pos(
            a_hat[4 * i + 2], a_hat[4 * i + 3],
            b_hat[4 * i + 2], b_hat[4 * i + 3], Q - gamma
        )
    return r


def poly_add(a: list[int], b: list[int]) -> list[int]:
    return [(a[i] + b[i]) % Q for i in range(N)]


def sample_ntt(seed_34: bytes) -> list[int]:
    """FIPS 203 Algorithm 7 - SampleNTT."""
    ctx = hashlib.shake_128(seed_34)
    stream = ctx.digest(840)
    coeffs: list[int] = []
    pos = 0
    while len(coeffs) < N and pos + 3 <= len(stream):
        b0 = stream[pos + 0]
        b1 = stream[pos + 1]
        b2 = stream[pos + 2]
        pos += 3
        d1 = b0 | ((b1 & 0x0F) << 8)
        d2 = (b1 >> 4) | (b2 << 4)
        if d1 < Q and len(coeffs) < N:
            coeffs.append(d1)
        if d2 < Q and len(coeffs) < N:
            coeffs.append(d2)
    return coeffs


def cbd3(buf: bytes) -> list[int]:
    """FIPS 203 Algorithm 8 - SamplePolyCBD with eta=3."""
    coeffs = []
    for i in range(0, 192, 3):
        b0 = buf[i]
        b1 = buf[i + 1]
        b2 = buf[i + 2]
        d = b0 | (b1 << 8) | (b2 << 16)
        for j in range(4):
            val = (d >> (6 * j)) & 0x3F
            a = (val & 1) + ((val >> 1) & 1) + ((val >> 2) & 1)
            b = ((val >> 3) & 1) + ((val >> 4) & 1) + ((val >> 5) & 1)
            coeffs.append((a - b) % Q)
    return coeffs


def cbd2(buf: bytes) -> list[int]:
    """FIPS 203 Algorithm 8 - SamplePolyCBD with eta=2."""
    coeffs = []
    for b in buf:
        val0 = b & 0x0F
        a0 = (val0 & 1) + ((val0 >> 1) & 1)
        b0 = ((val0 >> 2) & 1) + ((val0 >> 3) & 1)
        coeffs.append((a0 - b0) % Q)
        val1 = (b >> 4) & 0x0F
        a1 = (val1 & 1) + ((val1 >> 1) & 1)
        b1 = ((val1 >> 2) & 1) + ((val1 >> 3) & 1)
        coeffs.append((a1 - b1) % Q)
    return coeffs


def decompress_1(msg32: bytes) -> list[int]:
    """FIPS 203: Decompress1(m) -> mu."""
    r = [0] * N
    for i in range(32):
        for j in range(8):
            bit = (msg32[i] >> j) & 1
            r[8 * i + j] = bit * 1665
    return r


def compress_10(poly: list[int]) -> bytes:
    """FIPS 203: Compress10 and ByteEncode10 -> 320 bytes."""
    out = bytearray(320)
    pos = 0
    for i in range(N // 4):
        t = [0] * 4
        for j in range(4):
            u = poly[4 * i + j] % Q
            d0 = u << 10
            d0 += 1665
            d0 *= 1290167
            d0 &= 0xFFFFFFFFFFFFFFFF
            d0 >>= 32
            t[j] = d0 & 0x3FF
        out[pos + 0] = t[0] & 0xFF
        out[pos + 1] = ((t[0] >> 8) | (t[1] << 2)) & 0xFF
        out[pos + 2] = ((t[1] >> 6) | (t[2] << 4)) & 0xFF
        out[pos + 3] = ((t[2] >> 4) | (t[3] << 6)) & 0xFF
        out[pos + 4] = (t[3] >> 2) & 0xFF
        pos += 5
    return bytes(out)


def compress_4(poly: list[int]) -> bytes:
    """FIPS 203: Compress4 and ByteEncode4 -> 128 bytes."""
    out = bytearray(128)
    pos = 0
    for i in range(N // 8):
        t = [0] * 8
        for j in range(8):
            u = poly[8 * i + j] % Q
            d0 = (u << 4) + 1665
            d0 *= 80635
            d0 >>= 28
            t[j] = d0 & 0x0F
        out[pos + 0] = t[0] | (t[1] << 4)
        out[pos + 1] = t[2] | (t[3] << 4)
        out[pos + 2] = t[4] | (t[5] << 4)
        out[pos + 3] = t[6] | (t[7] << 4)
        pos += 4
    return bytes(out)


def kpke_encrypt_reference(ek: bytes, m: bytes, r: bytes) -> bytes:
    """FIPS 203 Algorithm 14 - K-PKE.Encrypt(ek, m, r)."""
    # 1. Unpack ek: t_hat[0..1], rho
    t_hat = [
        byte_decode_12(ek[0:384]),
        byte_decode_12(ek[384:768]),
    ]
    rho = ek[768:800]

    # 2. Regenerate A_hat^T (transposed column-row indexing)
    a_hat_t = [
        [sample_ntt(rho + bytes([i, j])) for j in range(K)]
        for i in range(K)
    ]

    # 3. Sample vector r (eta1 = 3)
    r_vec = [
        cbd3(hashlib.shake_256(r + bytes([0])).digest(192)),
        cbd3(hashlib.shake_256(r + bytes([1])).digest(192)),
    ]

    # 4. Sample error vector e1 (eta2 = 2)
    e1 = [
        cbd2(hashlib.shake_256(r + bytes([2])).digest(128)),
        cbd2(hashlib.shake_256(r + bytes([3])).digest(128)),
    ]

    # 5. Sample error e2 (eta2 = 2)
    e2 = cbd2(hashlib.shake_256(r + bytes([4])).digest(128))

    # 6. Transform r to NTT domain
    r_hat = [ntt(p) for p in r_vec]

    # 7. Compute u = INTT(A_hat^T * r_hat) + e1
    u = []
    for i in range(K):
        acc = [0] * N
        for j in range(K):
            prod = multiply_ntts(a_hat_t[i][j], r_hat[j])
            acc = poly_add(acc, prod)
        u.append(poly_add(intt(acc), e1[i]))

    # 8. Compute v = INTT(t_hat^T * r_hat) + e2 + Decompress1(m)
    acc_v = [0] * N
    for j in range(K):
        prod = multiply_ntts(t_hat[j], r_hat[j])
        acc_v = poly_add(acc_v, prod)
    v = poly_add(poly_add(intt(acc_v), e2), decompress_1(m))

    # 9. Compress and serialize
    c1 = b"".join(compress_10(p) for p in u)
    c2 = compress_4(v)
    return c1 + c2
