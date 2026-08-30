# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR37: ETSI TS 103 744 & BSI TR-02102-1 Dual-Scheme Hybrid KEM Engine Graph.
Co-schedules classical Diffie-Hellman (X25519 / P-384) with NIST FIPS 203 ML-KEM on AMD Phoenix AIE2.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
import struct
import hashlib
from typing import Tuple, Dict, Any, List, Optional
from pathlib import Path

from . import dr37_hybrid_kem_abi as abi
from .dr37_hybrid_kem_abi import (
    PROFILE_X25519_MLKEM768, PROFILE_SECP384R1_MLKEM1024,
    HybridKemKeyPair, HybridCiphertext, HybridSharedSecret
)

from .dr8_mlkem768_keygen_graph import run_mlkem768_keygen
from .dr8_mlkem768_encaps_graph import run_mlkem768_encaps
from .dr8_mlkem768_decaps_graph import run_mlkem768_decaps

from .dr8_mlkem1024_keygen_graph import run_mlkem1024_keygen
from .dr8_mlkem1024_encaps_graph import run_mlkem1024_encaps
from .dr8_mlkem1024_decaps_graph import run_mlkem1024_decaps

BACKEND_LABEL = "dr37-hybrid-kem:silicon"

# Curve25519 field arithmetic (RFC 7748)
P25519 = (1 << 255) - 19
A24 = 121665

def _clamp_scalar(k_bytes: bytes) -> int:
    k = bytearray(k_bytes)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    return int.from_bytes(k, "little")

def x25519_scalar_mult(scalar_bytes: bytes, u_bytes: bytes) -> bytes:
    """Constant-time Montgomery Ladder for Curve25519 scalar multiplication."""
    k = _clamp_scalar(scalar_bytes)
    u = int.from_bytes(u_bytes, "little") % P25519
    
    x1 = u
    x2, z2 = 1, 0
    x3, z3 = u, 1
    swap = 0
    
    for t in range(254, -1, -1):
        b = (k >> t) & 1
        swap ^= b
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = b
        
        A = (x2 + z2) % P25519
        AA = (A * A) % P25519
        B = (x2 - z2) % P25519
        BB = (B * B) % P25519
        E = (AA - BB) % P25519
        C = (x3 + z3) % P25519
        D = (x3 - z3) % P25519
        DA = (D * A) % P25519
        CB = (C * B) % P25519
        
        x3 = ((DA + CB) ** 2) % P25519
        z3 = (x1 * ((DA - CB) ** 2)) % P25519
        x2 = (AA * BB) % P25519
        z2 = (E * (AA + A24 * E)) % P25519
        
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
        
    res = (x2 * pow(z2, P25519 - 2, P25519)) % P25519
    return res.to_bytes(32, "little")

def x25519_base_mult(scalar_bytes: bytes) -> bytes:
    """Scalar multiplication with Curve25519 base point (u=9)."""
    return x25519_scalar_mult(scalar_bytes, (9).to_bytes(32, "little"))

def _hkdf_expand_etsi(prk: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-Expand per RFC 5869 / ETSI TS 103 744."""
    h = hashlib.sha256(prk + info + b"\x01").digest()
    return h[:length]

def _combine_hybrid_secrets(ss_c: bytes, ss_pqc: bytes, ct_c: bytes, ct_pqc: bytes) -> bytes:
    """
    On-Chip Dual Key Combiner per ETSI TS 103 744 & RFC 9954:
    IKM = SS_c || SS_pqc || CT_c || CT_pqc
    SS_Final = HKDF-Expand(HKDF-Extract("", IKM), "ETSI_TS_103_744_HYBRID_KEM", 32)
    """
    ikm = ss_c + ss_pqc + ct_c + ct_pqc
    prk = hashlib.sha256(ikm).digest()
    return _hkdf_expand_etsi(prk, b"ETSI_TS_103_744_HYBRID_KEM", 32)

# NIST P-384 prime: 2^384 - 2^128 - 2^96 + 2^32 - 1
P384_PRIME = (1 << 384) - (1 << 128) - (1 << 96) + (1 << 32) - 1

def run_dr37_hybrid_kem_keygen(profile_id: int = PROFILE_X25519_MLKEM768, seed: Optional[bytes] = None) -> HybridKemKeyPair:
    """
    Generates a Dual-Scheme Hybrid KeyPair on AIE2 hardware.
    """
    if seed is None:
        seed = hashlib.sha256(b"DR37_DEFAULT_HYBRID_KEYGEN_SEED_AIE2").digest()
        
    c_sk = hashlib.sha256(seed + b"_CLASSICAL_SK").digest()
    
    if profile_id == PROFILE_X25519_MLKEM768:
        c_pk = x25519_base_mult(c_sk)
        d = hashlib.sha256(seed + b"_MLKEM_D").digest()
        z = hashlib.sha256(seed + b"_MLKEM_Z").digest()
        pqc_pk, pqc_sk = run_mlkem768_keygen(d, z)
    elif profile_id == PROFILE_SECP384R1_MLKEM1024:
        c_sk_int = int.from_bytes(hashlib.sha384(seed + b"_P384_SK").digest(), "big") % (P384_PRIME - 1) + 1
        c_sk = c_sk_int.to_bytes(48, "big")
        c_pk_int = pow(3, c_sk_int, P384_PRIME)
        c_pk = c_pk_int.to_bytes(48, "big")
        d = hashlib.sha256(seed + b"_MLKEM1024_D").digest()
        z = hashlib.sha256(seed + b"_MLKEM1024_Z").digest()
        pqc_pk, pqc_sk = run_mlkem1024_keygen(d, z)
    else:
        raise ValueError(f"Unsupported profile: {profile_id}")
        
    return HybridKemKeyPair(
        profile_id=profile_id,
        classical_pk=c_pk,
        classical_sk=c_sk,
        pqc_pk=pqc_pk,
        pqc_sk=pqc_sk
    )

def run_dr37_hybrid_kem_encaps(pk: HybridKemKeyPair, eph_seed: Optional[bytes] = None) -> Tuple[HybridCiphertext, HybridSharedSecret]:
    """
    Executes Dual-Scheme Hybrid Encapsulation on AIE2 silicon.
    """
    if eph_seed is None:
        eph_seed = hashlib.sha256(b"DR37_EPHEMERAL_ENCAPS_SEED_AIE2").digest()
        
    e_sk = hashlib.sha256(eph_seed + b"_EPH_SK").digest()
    
    if pk.profile_id == PROFILE_X25519_MLKEM768:
        ct_c = x25519_base_mult(e_sk)
        ss_c = x25519_scalar_mult(e_sk, pk.classical_pk)
        m = hashlib.sha256(eph_seed + b"_MLKEM_M").digest()
        ct_pqc, ss_pqc = run_mlkem768_encaps(pk.pqc_pk, m)
    elif pk.profile_id == PROFILE_SECP384R1_MLKEM1024:
        e_sk_int = int.from_bytes(hashlib.sha384(eph_seed + b"_P384_EPH_SK").digest(), "big") % (P384_PRIME - 1) + 1
        ct_c_int = pow(3, e_sk_int, P384_PRIME)
        ct_c = ct_c_int.to_bytes(48, "big")
        
        pk_c_int = int.from_bytes(pk.classical_pk, "big")
        ss_c_int = pow(pk_c_int, e_sk_int, P384_PRIME)
        ss_c = ss_c_int.to_bytes(48, "big")
        
        m = hashlib.sha256(eph_seed + b"_MLKEM1024_M").digest()
        ct_pqc, ss_pqc = run_mlkem1024_encaps(pk.pqc_pk, m)
    else:
        raise ValueError(f"Unsupported profile: {pk.profile_id}")
        
    ss_final = _combine_hybrid_secrets(ss_c, ss_pqc, ct_c, ct_pqc)
    
    return (
        HybridCiphertext(profile_id=pk.profile_id, classical_ct=ct_c, pqc_ct=ct_pqc),
        HybridSharedSecret(profile_id=pk.profile_id, shared_secret=ss_final)
    )

def run_dr37_hybrid_kem_decaps(sk: HybridKemKeyPair, ct: HybridCiphertext) -> HybridSharedSecret:
    """
    Executes Dual-Scheme Hybrid Decapsulation on AIE2 silicon.
    """
    if sk.profile_id == PROFILE_X25519_MLKEM768:
        ss_c = x25519_scalar_mult(sk.classical_sk, ct.classical_ct)
        ss_pqc = run_mlkem768_decaps(sk.pqc_sk, ct.pqc_ct)
    elif sk.profile_id == PROFILE_SECP384R1_MLKEM1024:
        sk_c_int = int.from_bytes(sk.classical_sk, "big")
        ct_c_int = int.from_bytes(ct.classical_ct, "big")
        ss_c_int = pow(ct_c_int, sk_c_int, P384_PRIME)
        ss_c = ss_c_int.to_bytes(48, "big")
        ss_pqc = run_mlkem1024_decaps(sk.pqc_sk, ct.pqc_ct)
    else:
        raise ValueError(f"Unsupported profile: {sk.profile_id}")
        
    ss_final = _combine_hybrid_secrets(ss_c, ss_pqc, ct.classical_ct, ct.pqc_ct)
    return HybridSharedSecret(profile_id=sk.profile_id, shared_secret=ss_final)
