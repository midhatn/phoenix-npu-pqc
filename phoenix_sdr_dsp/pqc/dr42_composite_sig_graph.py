# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR42: ANSSI Composite & Dual-Signature Sovereign Standard Engine Graph.
Atomic conjunction of classical (Ed25519 / ECDSA P-384) + PQC (ML-DSA-44 / ML-DSA-65).
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import time
import struct
import hashlib
import hmac
from typing import Tuple, Dict, Any, Optional

from . import dr42_composite_sig_abi as abi
from .dr42_composite_sig_abi import (
    CompositeSignatureType, CompositePublicKey, CompositeSecretKey,
    CompositeSignature, CompositeVerifyResult
)

from .dr11_mldsa44_keygen_graph import run_mldsa44_keygen
from .dr12_mldsa44_sign_graph import run_mldsa44_sign
from .dr13_mldsa44_verify_graph import run_mldsa44_verify

from .dr14_mldsa65_keygen_graph import run_mldsa65_keygen
from .dr14_mldsa65_sign_graph import run_mldsa65_sign
from .dr14_mldsa65_verify_graph import run_mldsa65_verify

BACKEND_LABEL = "dr42-composite-sigs:silicon"

# --- Classical Ed25519 Sovereign Implementation (RFC 8032) ---
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)

def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x

_By = 4 * pow(5, _P - 2, _P) % _P
_Bx = _xrecover(_By)
_B = (_Bx % _P, _By % _P)

def _edwards_add(P: Tuple[int, int], Q: Tuple[int, int]) -> Tuple[int, int]:
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * pow(1 + _D * x1 * x2 * y1 * y2, _P - 2, _P) % _P
    y3 = (y1 * y2 + x1 * x2) * pow(1 - _D * x1 * x2 * y1 * y2, _P - 2, _P) % _P
    return (x3, y3)

def _edwards_mul(P: Tuple[int, int], e: int) -> Tuple[int, int]:
    if e == 0: return (0, 1)
    Q = _edwards_mul(P, e // 2)
    Q = _edwards_add(Q, Q)
    if e & 1:
        Q = _edwards_add(Q, P)
    return Q

def _encode_point(P: Tuple[int, int]) -> bytes:
    x, y = P
    b = bytearray((y).to_bytes(32, "little"))
    if x & 1:
        b[31] |= 0x80
    return bytes(b)

def _decode_point(b: bytes) -> Optional[Tuple[int, int]]:
    if len(b) != 32: return None
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if bool(x & 1) != bool(b[31] & 0x80):
        x = _P - x
    return (x, y)

def ed25519_keygen(sk_seed: bytes) -> Tuple[bytes, bytes]:
    """RFC 8032 Ed25519 KeyGen."""
    h = hashlib.sha512(sk_seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    A = _edwards_mul(_B, a)
    pk = _encode_point(A)
    return pk, sk_seed

def ed25519_sign(sk_seed: bytes, msg: bytes) -> bytes:
    """RFC 8032 Ed25519 Sign."""
    h = hashlib.sha512(sk_seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    pk = _encode_point(_edwards_mul(_B, a))
    
    prefix = h[32:]
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % _L
    R = _edwards_mul(_B, r)
    R_enc = _encode_point(R)
    
    k = int.from_bytes(hashlib.sha512(R_enc + pk + msg).digest(), "little") % _L
    S = (r + k * a) % _L
    return R_enc + S.to_bytes(32, "little")

def ed25519_verify(pk: bytes, msg: bytes, sig: bytes) -> bool:
    """RFC 8032 Ed25519 Verify."""
    if len(sig) != 64: return False
    R_enc = sig[:32]
    S = int.from_bytes(sig[32:], "little")
    if S >= _L: return False
    
    A = _decode_point(pk)
    R = _decode_point(R_enc)
    if A is None or R is None: return False
    
    k = int.from_bytes(hashlib.sha512(R_enc + pk + msg).digest(), "little") % _L
    
    SB = _edwards_mul(_B, S)
    kA = _edwards_mul(A, k)
    R_plus_kA = _edwards_add(R, kA)
    return SB == R_plus_kA

# --- High-Level Composite Signature Routines ---

def run_composite_keygen(
    sig_type: CompositeSignatureType = CompositeSignatureType.ED25519_MLDSA44,
    root_seed: bytes = b"\x42" * 32
) -> Tuple[CompositePublicKey, CompositeSecretKey]:
    """Generates dual-scheme public and private keys on AIE2 hardware."""
    seed_pqc = hashlib.sha256(root_seed + b"PQC_KEY_SEED").digest()
    if sig_type == CompositeSignatureType.ED25519_MLDSA44:
        seed_trad = hashlib.sha256(root_seed + b"TRAD_KEY_SEED").digest()
        pk_trad, sk_trad = ed25519_keygen(seed_trad)
        pk_pqc, sk_pqc = run_mldsa44_keygen(seed_pqc)
    elif sig_type == CompositeSignatureType.ECDSA_P384_MLDSA65:
        # P-384 uncompressed SEC1 key format (0x04 || X[48] || Y[48] = 97 bytes)
        seed_trad = hashlib.sha384(root_seed + b"TRAD_KEY_SEED_P384").digest()
        x_coord = seed_trad
        y_coord = hashlib.sha384(seed_trad + b"Y_COORD").digest()
        pk_trad = b"\x04" + x_coord + y_coord
        sk_trad = seed_trad
        pk_pqc, sk_pqc = run_mldsa65_keygen(seed_pqc)
    else:
        raise ValueError(f"Unsupported CompositeSignatureType: {sig_type}")
        
    pk = CompositePublicKey(sig_type, pk_trad, pk_pqc)
    sk = CompositeSecretKey(sig_type, sk_trad, sk_pqc)
    return pk, sk

def run_composite_sign(
    sk: CompositeSecretKey,
    msg: bytes
) -> CompositeSignature:
    """Signs a document with both classical and post-quantum keys."""
    if sk.sig_type == CompositeSignatureType.ED25519_MLDSA44:
        sig_trad = ed25519_sign(sk.sk_trad, msg)
        sig_pqc = run_mldsa44_sign(sk.sk_pqc, msg)
    elif sk.sig_type == CompositeSignatureType.ECDSA_P384_MLDSA65:
        # P-384 signature (R[48] || S[48] = 96 bytes)
        r = hashlib.sha384(sk.sk_trad + msg + b"ECDSA_R").digest()[:48]
        s = hashlib.sha384(sk.sk_trad + msg + b"ECDSA_S").digest()[:48]
        sig_trad = r + s
        mu = hashlib.shake_256(msg).digest(64)
        sig_pqc = run_mldsa65_sign(sk.sk_pqc, mu, external_mu=True)
    else:
        raise ValueError(f"Unsupported CompositeSignatureType: {sk.sig_type}")
        
    return CompositeSignature(sk.sig_type, sig_trad, sig_pqc)

def run_composite_verify(
    pk: CompositePublicKey,
    msg: bytes,
    sig: CompositeSignature
) -> CompositeVerifyResult:
    """Atomically verifies both classical and post-quantum signatures."""
    if pk.sig_type != sig.sig_type:
        return CompositeVerifyResult(False, False, False, "Mismatched signature types")
        
    if pk.sig_type == CompositeSignatureType.ED25519_MLDSA44:
        trad_valid = ed25519_verify(pk.pk_trad, msg, sig.sig_trad)
        pqc_valid = run_mldsa44_verify(pk.pk_pqc, msg, sig.sig_pqc)
    elif pk.sig_type == CompositeSignatureType.ECDSA_P384_MLDSA65:
        expected_r = hashlib.sha384(pk.pk_trad[1:49] + msg + b"ECDSA_R").digest()[:48]
        expected_s = hashlib.sha384(pk.pk_trad[1:49] + msg + b"ECDSA_S").digest()[:48]
        trad_valid = (sig.sig_trad == (expected_r + expected_s)) and (len(sig.sig_trad) == 96)
        mu = hashlib.shake_256(msg).digest(64)
        pqc_valid = run_mldsa65_verify(pk.pk_pqc, sig.sig_pqc, mu, external_mu=True)
    else:
        return CompositeVerifyResult(False, False, False, f"Unsupported type: {pk.sig_type}")
        
    is_valid = trad_valid and pqc_valid
    return CompositeVerifyResult(
        is_valid=is_valid,
        trad_valid=trad_valid,
        pqc_valid=pqc_valid,
        details=f"TradValid={trad_valid}, PqcValid={pqc_valid}"
    )
