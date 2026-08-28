# SPDX-License-Identifier: Apache-2.0
"""Pure-Python reference oracle for FIPS 203 ML-KEM-512 ML-KEM.Decaps (Algorithm 17)."""
from __future__ import annotations

import hashlib
from tests.pqc_device_resident.dr4_reference import kpke_decrypt_reference
from tests.pqc_device_resident.dr3_reference import kpke_encrypt_reference

def shake256(data: bytes, out_len: int) -> bytes:
    """FIPS 202 SHAKE256(data, d)."""
    return hashlib.shake_256(data).digest(out_len)

def sha3_512(data: bytes) -> bytes:
    """FIPS 202 SHA3-512(data)."""
    return hashlib.sha3_512(data).digest()

def mlkem512_decaps_reference(dk: bytes, c: bytes) -> bytes:
    """FIPS 203 Algorithm 17 ML-KEM.Decaps(dk, c).

    Inputs:
      dk: 1632 bytes decapsulation key
          - dk_PKE = dk[0:768]
          - ek = dk[768:1568]
          - H(ek) = dk[1568:1600]
          - z = dk[1600:1632]
      c: 768 bytes ciphertext

    Output:
      K: 32 bytes shared secret
    """
    assert len(dk) == 1632, f"Expected 1632 B dk, got {len(dk)}"
    assert len(c) == 768, f"Expected 768 B c, got {len(c)}"

    dk_pke = dk[0:768]
    ek = dk[768:1568]
    h_ek = dk[1568:1600]
    z = dk[1600:1632]

    # Step 1: m' = K-PKE.Decrypt(dk_PKE, c)
    m_prime = kpke_decrypt_reference(dk_pke, c)

    # Step 2: (K_bar_prime, r_prime) = G(m' || H(ek))
    g_out = sha3_512(m_prime + h_ek)
    k_bar_prime = g_out[0:32]
    r_prime = g_out[32:64]

    # Step 3: K_bar = J(z || c, 32)
    k_bar = shake256(z + c, 32)

    # Step 4: c' = K-PKE.Encrypt(ek, m_prime, r_prime)
    c_prime = kpke_encrypt_reference(ek, m_prime, r_prime)

    # Step 5: Constant-time comparison between c and c'
    # In FIPS 203 Algorithm 17: if c' == c return K_bar_prime else return K_bar
    diff = 0
    for b1, b2 in zip(c, c_prime):
        diff |= (b1 ^ b2)

    if diff == 0:
        return k_bar_prime
    else:
        return k_bar
