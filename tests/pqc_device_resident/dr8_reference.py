# SPDX-License-Identifier: Apache-2.0
"""Reference oracle for NIST FIPS 203 ML-KEM-768 and ML-KEM-1024 across all operations.

Supports:
- KeyGen (Algorithm 15, 12)
- Encaps (Algorithm 16, 13)
- Decaps (Algorithm 17, 14)
for parameter sets:
- ML-KEM-512  (k=2, eta1=3, eta2=2, du=10, dv=4)
- ML-KEM-768  (k=3, eta1=2, eta2=2, du=10, dv=4)
- ML-KEM-1024 (k=4, eta1=2, eta2=2, du=11, dv=5)
"""
import hashlib
from typing import NamedTuple, Tuple

N = 256
Q = 3329
ZETAS = [
    1, 1729, 2580, 3289, 2642, 630, 1897, 848,
    1062, 1919, 193, 797, 2786, 3260, 569, 1746,
    296, 2447, 1339, 1476, 3046, 56, 2240, 1333,
    1426, 2094, 535, 2882, 2393, 2879, 1974, 821,
    289, 331, 3253, 1756, 1197, 2304, 2277, 2055,
    650, 1977, 2513, 632, 2865, 33, 1320, 1915,
    2319, 1435, 807, 452, 1438, 2868, 1534, 2402,
    2647, 2617, 1481, 648, 2474, 3110, 1227, 910,
    17, 2761, 583, 2649, 1637, 723, 2288, 1100,
    1409, 2662, 3281, 233, 756, 2156, 3015, 3050,
    1703, 1651, 2789, 1789, 1847, 952, 1461, 2687,
    939, 2308, 2437, 2388, 733, 2337, 268, 641,
    1584, 2298, 2037, 3220, 375, 2549, 2090, 1645,
    1063, 319, 2773, 757, 2099, 561, 2466, 2594,
    2804, 1092, 403, 1026, 1143, 2150, 2775, 886,
    1722, 1212, 1874, 1029, 2110, 2935, 885, 2154,
]

class Params(NamedTuple):
    k: int
    eta1: int
    eta2: int
    du: int
    dv: int
    ek_len: int
    dk_len: int
    c_len: int

PARAMS_512 = Params(k=2, eta1=3, eta2=2, du=10, dv=4, ek_len=800, dk_len=1632, c_len=768)
PARAMS_768 = Params(k=3, eta1=2, eta2=2, du=10, dv=4, ek_len=1184, dk_len=2400, c_len=1088)
PARAMS_1024 = Params(k=4, eta1=2, eta2=2, du=11, dv=5, ek_len=1568, dk_len=3168, c_len=1568)

def get_params(name_or_k):
    if name_or_k in (512, "ML-KEM-512", 2): return PARAMS_512
    if name_or_k in (768, "ML-KEM-768", 3): return PARAMS_768
    if name_or_k in (1024, "ML-KEM-1024", 4): return PARAMS_1024
    raise ValueError(f"Unknown parameter set: {name_or_k}")

def ntt(r):
    a = list(r)
    k = 1
    length = 128
    while length >= 2:
        start = 0
        while start < 256:
            zeta = ZETAS[k]
            k += 1
            for j in range(start, start + length):
                t = (zeta * a[j + length]) % Q
                a[j + length] = (a[j] - t) % Q
                a[j] = (a[j] + t) % Q
            start += 2 * length
        length //= 2
    return a

def intt(r):
    a = list(r)
    k = 127
    length = 2
    while length <= 128:
        start = 0
        while start < 256:
            zeta = ZETAS[k]
            k -= 1
            for j in range(start, start + length):
                t = a[j]
                a[j] = (t + a[j + length]) % Q
                a[j + length] = (zeta * (a[j + length] - t)) % Q
            start += 2 * length
        length *= 2
    f = 3303 # 128^-1 mod 3329
    return [(x * f) % Q for x in a]

def basemul(a0, a1, b0, b1, zeta):
    r0 = (a1 * b1 * zeta + a0 * b0) % Q
    r1 = (a0 * b1 + a1 * b0) % Q
    return r0, r1

def multiply_ntts(a, b):
    c = [0] * 256
    for i in range(64):
        zeta = ZETAS[64 + i]
        r0, r1 = basemul(a[4 * i + 0], a[4 * i + 1], b[4 * i + 0], b[4 * i + 1], zeta)
        r2, r3 = basemul(a[4 * i + 2], a[4 * i + 3], b[4 * i + 2], b[4 * i + 3], -zeta % Q)
        c[4 * i + 0] = r0
        c[4 * i + 1] = r1
        c[4 * i + 2] = r2
        c[4 * i + 3] = r3
    return c

def sample_ntt(b):
    stream = hashlib.shake_128(b).digest(168 * 5)
    coeffs = []
    for off in range(0, len(stream) - 2, 3):
        d1 = stream[off] + 256 * (stream[off + 1] & 0x0F)
        d2 = (stream[off + 1] >> 4) + 16 * stream[off + 2]
        if d1 < Q and len(coeffs) < 256:
            coeffs.append(d1)
        if d2 < Q and len(coeffs) < 256:
            coeffs.append(d2)
        if len(coeffs) == 256:
            break
    return coeffs

def prf_eta(s, b, eta):
    out_len = 64 * eta
    buf = hashlib.shake_256(s + bytes([b])).digest(out_len)
    coeffs = []
    if eta == 2:
        for i in range(128):
            byte = buf[i]
            b0 = (byte >> 0) & 1
            b1 = (byte >> 1) & 1
            b2 = (byte >> 2) & 1
            b3 = (byte >> 3) & 1
            coeffs.append(((b0 + b1) - (b2 + b3)) % Q)
            b4 = (byte >> 4) & 1
            b5 = (byte >> 5) & 1
            b6 = (byte >> 6) & 1
            b7 = (byte >> 7) & 1
            coeffs.append(((b4 + b5) - (b6 + b7)) % Q)
    elif eta == 3:
        for i in range(64):
            val = buf[3 * i] | (buf[3 * i + 1] << 8) | (buf[3 * i + 2] << 16)
            for j in range(4):
                bits = (val >> (6 * j)) & 0x3F
                b0 = (bits >> 0) & 1
                b1 = (bits >> 1) & 1
                b2 = (bits >> 2) & 1
                b3 = (bits >> 3) & 1
                b4 = (bits >> 4) & 1
                b5 = (bits >> 5) & 1
                coeffs.append(((b0 + b1 + b2) - (b3 + b4 + b5)) % Q)
    return coeffs

def byte_encode_12(poly):
    out = bytearray(384)
    for i in range(128):
        t0 = poly[2 * i] & 0xFFF
        t1 = poly[2 * i + 1] & 0xFFF
        out[3 * i + 0] = t0 & 0xFF
        out[3 * i + 1] = (t0 >> 8) | ((t1 & 0x0F) << 4)
        out[3 * i + 2] = t1 >> 4
    return bytes(out)

def byte_decode_12(b):
    out = [0] * 256
    for i in range(128):
        b0 = b[3 * i + 0]
        b1 = b[3 * i + 1]
        b2 = b[3 * i + 2]
        out[2 * i] = b0 | ((b1 & 0x0F) << 8)
        out[2 * i + 1] = (b1 >> 4) | (b2 << 4)
    return out

def compress(x, d):
    return ((x << d) + 1664) // Q & ((1 << d) - 1)

def decompress(y, d):
    return ((y * Q) + (1 << (d - 1))) >> d

def byte_encode_du(poly, du):
    if du == 10:
        out = bytearray(320)
        for i in range(64):
            t0 = compress(poly[4 * i + 0], 10)
            t1 = compress(poly[4 * i + 1], 10)
            t2 = compress(poly[4 * i + 2], 10)
            t3 = compress(poly[4 * i + 3], 10)
            out[5 * i + 0] = t0 & 0xFF
            out[5 * i + 1] = (t0 >> 8) | ((t1 & 0x3F) << 2)
            out[5 * i + 2] = (t1 >> 6) | ((t2 & 0x0F) << 4)
            out[5 * i + 3] = (t2 >> 4) | ((t3 & 0x03) << 6)
            out[5 * i + 4] = t3 >> 2
        return bytes(out)
    elif du == 11:
        out = bytearray(352)
        for i in range(32):
            t = [compress(poly[8 * i + j], 11) for j in range(8)]
            # 8 coeffs * 11 bits = 88 bits = 11 bytes
            val = 0
            for j in range(8):
                val |= (t[j] << (11 * j))
            for b in range(11):
                out[11 * i + b] = (val >> (8 * b)) & 0xFF
        return bytes(out)

def byte_decode_du(data, du):
    poly = [0] * 256
    if du == 10:
        for i in range(64):
            p = data[5 * i : 5 * i + 5]
            w0 = p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24)
            c0 = w0 & 0x3FF
            c1 = (w0 >> 10) & 0x3FF
            c2 = (w0 >> 20) & 0x3FF
            c3 = ((w0 >> 30) & 3) | (p[4] << 2)
            poly[4 * i + 0] = decompress(c0, 10)
            poly[4 * i + 1] = decompress(c1, 10)
            poly[4 * i + 2] = decompress(c2, 10)
            poly[4 * i + 3] = decompress(c3, 10)
    elif du == 11:
        for i in range(32):
            chunk = data[11 * i : 11 * i + 11]
            val = int.from_bytes(chunk, 'little')
            for j in range(8):
                c = (val >> (11 * j)) & 0x7FF
                poly[8 * i + j] = decompress(c, 11)
    return poly

def byte_encode_dv(poly, dv):
    if dv == 4:
        out = bytearray(128)
        for i in range(128):
            t0 = compress(poly[2 * i + 0], 4)
            t1 = compress(poly[2 * i + 1], 4)
            out[i] = t0 | (t1 << 4)
        return bytes(out)
    elif dv == 5:
        out = bytearray(160)
        for i in range(32):
            t = [compress(poly[8 * i + j], 5) for j in range(8)]
            # 8 coeffs * 5 bits = 40 bits = 5 bytes
            val = 0
            for j in range(8):
                val |= (t[j] << (5 * j))
            for b in range(5):
                out[5 * i + b] = (val >> (8 * b)) & 0xFF
        return bytes(out)

def byte_decode_dv(data, dv):
    poly = [0] * 256
    if dv == 4:
        for i in range(128):
            c0 = data[i] & 0x0F
            c1 = (data[i] >> 4) & 0x0F
            poly[2 * i + 0] = decompress(c0, 4)
            poly[2 * i + 1] = decompress(c1, 4)
    elif dv == 5:
        for i in range(32):
            chunk = data[5 * i : 5 * i + 5]
            val = int.from_bytes(chunk, 'little')
            for j in range(8):
                c = (val >> (5 * j)) & 0x1F
                poly[8 * i + j] = decompress(c, 5)
    return poly

def mlkem_keygen(d: bytes, z: bytes, params: Params) -> Tuple[bytes, bytes]:
    k = params.k
    g_out = hashlib.sha3_512(d + bytes([k])).digest()
    rho = g_out[:32]
    sigma = g_out[32:64]

    # Sample s and e
    s_hat = []
    for i in range(k):
        s_i = prf_eta(sigma, i, params.eta1)
        s_hat.append(ntt(s_i))

    e_hat = []
    for i in range(k):
        e_i = prf_eta(sigma, k + i, params.eta1)
        e_hat.append(ntt(e_i))

    # A_hat[row][col] = SampleNTT(rho || col || row)
    t_hat = []
    for row in range(k):
        acc = [0] * 256
        for col in range(k):
            a_elem = sample_ntt(rho + bytes([col, row]))
            prod = multiply_ntts(a_elem, s_hat[col])
            for idx in range(256):
                acc[idx] = (acc[idx] + prod[idx]) % Q
        for idx in range(256):
            acc[idx] = (acc[idx] + e_hat[row][idx]) % Q
        t_hat.append(acc)

    ek_bytes = b"".join(byte_encode_12(t_hat[i]) for i in range(k)) + rho
    dk_pke = b"".join(byte_encode_12(s_hat[i]) for i in range(k))
    h_ek = hashlib.sha3_256(ek_bytes).digest()
    dk_bytes = dk_pke + ek_bytes + h_ek + z

    return ek_bytes, dk_bytes

def mlkem_encaps(ek: bytes, m: bytes, params: Params) -> Tuple[bytes, bytes]:
    k = params.k
    h_ek = hashlib.sha3_256(ek).digest()
    g_out = hashlib.sha3_512(m + h_ek).digest()
    k_bar = g_out[:32]
    r = g_out[32:64]

    t_hat = [byte_decode_12(ek[384 * i : 384 * (i + 1)]) for i in range(k)]
    rho = ek[384 * k : 384 * k + 32]

    # Sample y (r_prime)
    y_hat = []
    for i in range(k):
        y_i = prf_eta(r, i, params.eta1)
        y_hat.append(ntt(y_i))

    # Sample e1
    e1 = []
    for i in range(k):
        e1.append(prf_eta(r, k + i, params.eta2))

    # Sample e2
    e2 = prf_eta(r, 2 * k, params.eta2)

    # u = INTT(A^T * y_hat) + e1
    u = []
    for row in range(k):
        acc = [0] * 256
        for col in range(k):
            # A^T[row][col] = A[col][row] = SampleNTT(rho || row || col)
            a_elem = sample_ntt(rho + bytes([row, col]))
            prod = multiply_ntts(a_elem, y_hat[col])
            for idx in range(256):
                acc[idx] = (acc[idx] + prod[idx]) % Q
        u_poly = intt(acc)
        for idx in range(256):
            u_poly[idx] = (u_poly[idx] + e1[row][idx]) % Q
        u.append(u_poly)

    # v = INTT(t_hat^T * y_hat) + e2 + mu(m)
    acc = [0] * 256
    for i in range(k):
        prod = multiply_ntts(t_hat[i], y_hat[i])
        for idx in range(256):
            acc[idx] = (acc[idx] + prod[idx]) % Q
    v_poly = intt(acc)
    # Add e2 + mu
    for idx in range(256):
        bit = (m[idx >> 3] >> (idx & 7)) & 1
        mu = 1665 if bit else 0
        v_poly[idx] = (v_poly[idx] + e2[idx] + mu) % Q

    c_u = b"".join(byte_encode_du(u[i], params.du) for i in range(k))
    c_v = byte_encode_dv(v_poly, params.dv)
    ciphertext = c_u + c_v

    # K = SHAKE256(K_bar || H(c), 32)
    # Note: in FIPS 203 ML-KEM.Encaps:
    # (K_bar, r) = G(m || H(ek))
    # c = K-PKE.Encrypt(ek, m, r)
    # K = K_bar (where K_bar is first 32 bytes of G)
    return ciphertext, k_bar

def mlkem_decaps(dk: bytes, c: bytes, params: Params) -> bytes:
    k = params.k
    dk_pke_len = 384 * k
    ek_len = 384 * k + 32
    dk_pke = dk[:dk_pke_len]
    ek = dk[dk_pke_len : dk_pke_len + ek_len]
    h_ek = dk[dk_pke_len + ek_len : dk_pke_len + ek_len + 32]
    z = dk[dk_pke_len + ek_len + 32 : dk_pke_len + ek_len + 64]

    s_hat = [byte_decode_12(dk_pke[384 * i : 384 * (i + 1)]) for i in range(k)]

    # Decode c -> u, v
    u_len = 32 * params.du
    u = []
    for i in range(k):
        u_bytes = c[u_len * i : u_len * (i + 1)]
        u.append(byte_decode_du(u_bytes, params.du))
    v_bytes = c[u_len * k :]
    v = byte_decode_dv(v_bytes, params.dv)

    # m' = Compress1(v - INTT(s_hat^T * NTT(u)))
    acc = [0] * 256
    for i in range(k):
        u_hat = ntt(u[i])
        prod = multiply_ntts(s_hat[i], u_hat)
        for idx in range(256):
            acc[idx] = (acc[idx] + prod[idx]) % Q
    w = intt(acc)

    m_prime = bytearray(32)
    for idx in range(256):
        diff = (v[idx] - w[idx]) % Q
        bit = 1 if (diff > 832 and diff < 2497) else 0
        m_prime[idx >> 3] |= (bit << (idx & 7))
    m_prime = bytes(m_prime)

    # Re-encrypt
    c_prime, k_bar_prime = mlkem_encaps(ek, m_prime, params)
    k_bar = hashlib.shake_256(z + c).digest(32)

    return k_bar_prime if c == c_prime else k_bar
