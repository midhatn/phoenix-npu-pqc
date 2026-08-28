# SPDX-License-Identifier: Apache-2.0
"""Pure-Python reference implementation of FIPS 203 ML-KEM-512 ML-KEM.KeyGen (Algorithm 15)."""
from __future__ import annotations

import hashlib
from tests.pqc_device_resident.dr3_reference import (
    Q, N, ZETAS, ntt, multiply_ntts
)

def byte_encode_12(coeffs: list[int]) -> bytes:
    out = bytearray(384)
    for i in range(128):
        c0 = coeffs[2 * i] & 0x0FFF
        c1 = coeffs[2 * i + 1] & 0x0FFF
        out[3 * i + 0] = c0 & 0xFF
        out[3 * i + 1] = ((c0 >> 8) & 0x0F) | ((c1 & 0x0F) << 4)
        out[3 * i + 2] = (c1 >> 4) & 0xFF
    return bytes(out)

def cbd3(b: bytes) -> list[int]:
    coeffs = []
    for i in range(64):
        chunk = b[3*i : 3*(i+1)]
        t = chunk[0] | (chunk[1] << 8) | (chunk[2] << 16)
        d = t & 0x00249249
        d += (t >> 1) & 0x00249249
        d += (t >> 2) & 0x00249249
        for j in range(4):
            a = (d >> (6 * j)) & 0x07
            b_val = (d >> (6 * j + 3)) & 0x07
            coeffs.append((a - b_val) % Q)
    return coeffs

def prf_eta(s: bytes, b: int) -> bytes:
    ctx = hashlib.shake_256()
    ctx.update(s + bytes([b]))
    return ctx.digest(192)

def sample_ntt(rho: bytes, j: int, i: int) -> list[int]:
    ctx = hashlib.shake_128()
    ctx.update(rho + bytes([j, i]))
    coeffs = []
    offset = 0
    # Stream blocks of 168 bytes
    buf = b""
    while len(coeffs) < 256:
        if offset + 3 > len(buf):
            buf += ctx.digest(168 * 4)[len(buf):]
        d1 = buf[offset] | ((buf[offset + 1] & 0x0F) << 8)
        d2 = (buf[offset + 1] >> 4) | (buf[offset + 2] << 4)
        offset += 3
        if d1 < Q and len(coeffs) < 256:
            coeffs.append(d1)
        if d2 < Q and len(coeffs) < 256:
            coeffs.append(d2)
    return coeffs

def mlkem512_keygen_reference(d: bytes, z: bytes) -> tuple[bytes, bytes]:
    """FIPS 203 Algorithm 15 ML-KEM.KeyGen_internal(d, z).
    
    Inputs:
      d: 32 bytes seed
      z: 32 bytes implicit rejection seed
    Outputs:
      (ek, dk): ek (800 bytes), dk (1632 bytes)
    """
    assert len(d) == 32
    assert len(z) == 32
    
    # 1. G(d || 2) -> (rho, sigma)
    g_out = hashlib.sha3_512(d + b"\x02").digest()
    rho = g_out[:32]
    sigma = g_out[32:]
    
    # 2. Public matrix A_hat[i, j] = SampleNTT(rho || j || i)
    A_hat = [
        [sample_ntt(rho, 0, 0), sample_ntt(rho, 1, 0)],
        [sample_ntt(rho, 0, 1), sample_ntt(rho, 1, 1)]
    ]
    
    # 3. Noise vectors s and e
    s = [cbd3(prf_eta(sigma, 0)), cbd3(prf_eta(sigma, 1))]
    e = [cbd3(prf_eta(sigma, 2)), cbd3(prf_eta(sigma, 3))]
    
    s_hat = [ntt(s[0]), ntt(s[1])]
    e_hat = [ntt(e[0]), ntt(e[1])]
    
    # 4. Matrix-vector multiplication t_hat = A_hat * s_hat + e_hat
    t_hat = [
        [(multiply_ntts(A_hat[0][0], s_hat[0])[i] + multiply_ntts(A_hat[0][1], s_hat[1])[i] + e_hat[0][i]) % Q for i in range(256)],
        [(multiply_ntts(A_hat[1][0], s_hat[0])[i] + multiply_ntts(A_hat[1][1], s_hat[1])[i] + e_hat[1][i]) % Q for i in range(256)]
    ]
    
    # 5. PKE key encoding
    ek_pke = byte_encode_12(t_hat[0]) + byte_encode_12(t_hat[1]) + rho
    dk_pke = byte_encode_12(s_hat[0]) + byte_encode_12(s_hat[1])
    
    # 6. Full decapsulation key assembly
    h_ek = hashlib.sha3_256(ek_pke).digest()
    dk = dk_pke + ek_pke + h_ek + z
    ek = ek_pke
    
    return ek, dk
