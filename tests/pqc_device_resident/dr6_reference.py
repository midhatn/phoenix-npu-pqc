# SPDX-License-Identifier: Apache-2.0
"""Independent pure-Python reference oracle for ML-KEM-512 ML-KEM.Encaps (FIPS 203 Algorithm 16)."""
from __future__ import annotations

import hashlib
from tests.pqc_device_resident.dr3_reference import kpke_encrypt_reference


def mlkem512_encaps_reference(ek: bytes, m: bytes) -> tuple[bytes, bytes]:
    """FIPS 203 Algorithm 16 - ML-KEM.Encaps(ek) using deterministic test seed m.
    
    Returns:
        (c, K): 768-byte ciphertext and 32-byte shared key.
    """
    if len(ek) != 800:
        raise ValueError(f"Invalid ek length: {len(ek)} (expected 800)")
    if len(m) != 32:
        raise ValueError(f"Invalid m length: {len(m)} (expected 32)")

    # 1. H(ek) = SHA3-256(ek) (32 bytes)
    h_ek = hashlib.sha3_256(ek).digest()

    # 2. (K_bar, r) = G(m || H(ek)) = SHA3-512(m || H(ek)) (64 bytes)
    g_out = hashlib.sha3_512(m + h_ek).digest()
    k_bar = g_out[:32]
    r = g_out[32:]

    # 3. c = K-PKE.Encrypt(ek, m, r) (768 bytes)
    c = kpke_encrypt_reference(ek, m, r)

    # 4. K = K_bar (32 bytes)
    k = k_bar

    return c, k
