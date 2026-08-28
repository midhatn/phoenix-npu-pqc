# SPDX-License-Identifier: Apache-2.0
"""Pure-Python reference implementation of FIPS 203 ML-KEM-512 K-PKE.Decrypt (Algorithm 14)."""
from __future__ import annotations

from tests.pqc_device_resident.dr3_reference import (
    Q, N, ZETAS, byte_decode_12, ntt, intt, multiply_ntts
)

def byte_decode_10(b: bytes) -> list[int]:
    coeffs = []
    for i in range(len(b) // 5):
        chunk = b[5 * i : 5 * (i + 1)]
        w0 = chunk[0] | (chunk[1] << 8) | (chunk[2] << 16) | (chunk[3] << 24)
        c0 = w0 & 0x3FF
        c1 = (w0 >> 10) & 0x3FF
        c2 = (w0 >> 20) & 0x3FF
        c3 = ((w0 >> 30) & 3) | (chunk[4] << 2)
        coeffs.extend([c0, c1, c2, c3])
    return coeffs

def decompress_10(c: list[int]) -> list[int]:
    return [((x * 3329 + 512) >> 10) for x in c]

def byte_decode_4(b: bytes) -> list[int]:
    coeffs = []
    for byte in b:
        coeffs.append(byte & 0x0F)
        coeffs.append((byte >> 4) & 0x0F)
    return coeffs

def decompress_4(c: list[int]) -> list[int]:
    return [((x * 3329 + 8) >> 4) for x in c]

def compress_1(w: list[int]) -> bytes:
    bits = [1 if (833 <= x <= 2496) else 0 for x in w]
    out = bytearray(32)
    for i in range(256):
        if bits[i]:
            out[i >> 3] |= (1 << (i & 7))
    return bytes(out)

def kpke_decrypt_reference(dk_pke: bytes, c: bytes) -> bytes:
    """FIPS 203 Algorithm 14 K-PKE.Decrypt(dk_PKE, c).
    
    Inputs:
      dk_pke: 768 bytes (ByteEncode_12(s_hat[0]) || ByteEncode_12(s_hat[1]))
      c: 768 bytes (c1[640] || c2[128])
    Output:
      m: 32 bytes plaintext
    """
    assert len(dk_pke) == 768, f"Expected 768 B dk_pke, got {len(dk_pke)}"
    assert len(c) == 768, f"Expected 768 B c, got {len(c)}"
    
    # 1. Decode s_hat vector
    s_hat = [byte_decode_12(dk_pke[0:384]), byte_decode_12(dk_pke[384:768])]
    
    # 2. Decompress u vector
    c1 = c[0:640]
    u = [
        decompress_10(byte_decode_10(c1[0:320])),
        decompress_10(byte_decode_10(c1[320:640]))
    ]
    
    # 3. Decompress v
    c2 = c[640:768]
    v = decompress_4(byte_decode_4(c2))
    
    # 4. Transform u to NTT domain
    u_hat = [ntt(u[0]), ntt(u[1])]
    
    # 5. Inner product in NTT domain
    acc = [(multiply_ntts(s_hat[0], u_hat[0])[i] + multiply_ntts(s_hat[1], u_hat[1])[i]) % Q for i in range(256)]
    
    # 6. Inverse NTT
    w_poly = intt(acc)
    
    # 7. Subtract from v
    w = [(v[i] - w_poly[i]) % Q for i in range(256)]
    
    # 8. Compress_1 and return 32-byte message
    return compress_1(w)
