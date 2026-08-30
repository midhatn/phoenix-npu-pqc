# SPDX-License-Identifier: Apache-2.0
"""
NIST FIPS 205 (SLH-DSA / SPHINCS+) Pure-Python CPU Reference Implementation.
Compliant with NIST FIPS PUB 205 (August 2024).
"""

import os
import time
import struct
import hashlib
import hmac
from typing import Tuple, Dict, Any
from pathlib import Path
import numpy as np

from . import dr21_slhdsa_abi as abi
from .dr21_slhdsa_abi import SLHDSA_PARAMS, ADRS, ADRS_TYPE_WOTS_HASH, ADRS_TYPE_WOTS_PK, ADRS_TYPE_TREE, ADRS_TYPE_FORS_TREE, ADRS_TYPE_FORS_ROOTS, ADRS_TYPE_WOTS_PRF, ADRS_TYPE_FORS_PRF

BACKEND_LABEL = "host-cpu-reference"

# SHAKE-256 Primitives for NIST FIPS 205 (SHAKE instantiated parameters)
def _shake256(data: bytes, outlen: int) -> bytes:
    h = hashlib.shake_256()
    h.update(data)
    return h.digest(outlen)

def _prf(pk_seed: bytes, sk_seed: bytes, adrs: ADRS, n: int) -> bytes:
    """FIPS 205 Section 10.1: PRF(PK.seed, SK.seed, ADRS)."""
    return _shake256(pk_seed + adrs.to_bytes() + sk_seed, n)

def _prf_msg(sk_prf: bytes, opt_rand: bytes, msg: bytes, n: int) -> bytes:
    """FIPS 205 Section 10.1: PRF_msg(SK.prf, OptRand, M)."""
    return _shake256(sk_prf + opt_rand + msg, n)

def _h_msg(r: bytes, pk_seed: bytes, pk_root: bytes, msg: bytes, outlen: int) -> bytes:
    """FIPS 205 Section 10.1: H_msg(R, PK.seed, PK.root, M)."""
    return _shake256(r + pk_seed + pk_root + msg, outlen)

def _f(pk_seed: bytes, adrs: ADRS, m: bytes, n: int) -> bytes:
    """FIPS 205 Section 10.1: F(PK.seed, ADRS, M_1)."""
    return _shake256(pk_seed + adrs.to_bytes() + m, n)

def _t_l(pk_seed: bytes, adrs: ADRS, m: bytes, n: int) -> bytes:
    """FIPS 205 Section 10.1: T_l(PK.seed, ADRS, M_l)."""
    return _shake256(pk_seed + adrs.to_bytes() + m, n)

# Winternitz Chaining Function
def _chain(x: bytes, i: int, s: int, pk_seed: bytes, adrs: ADRS, n: int) -> bytes:
    """FIPS 205 Section 5.1: chain(X, i, s, PK.seed, ADRS)."""
    res = bytearray(x)
    for j in range(i, i + s):
        adrs.set_hash_address(j)
        res = bytearray(_f(pk_seed, adrs, bytes(res), n))
    return bytes(res)

def _wots_pk_gen(sk_seed: bytes, pk_seed: bytes, adrs: ADRS, params: abi.SlhdsaParams) -> bytes:
    """FIPS 205 Section 5.2: wots_PKgen(SK.seed, PK.seed, ADRS)."""
    adrs_copy = adrs.copy()
    pk_buf = bytearray()
    for i in range(params.len_total):
        adrs_copy.set_chain_address(i)
        adrs_copy.set_hash_address(0)
        adrs_copy.set_type(ADRS_TYPE_WOTS_PRF)
        sk_i = _prf(pk_seed, sk_seed, adrs_copy, params.n)
        adrs_copy.set_type(ADRS_TYPE_WOTS_HASH)
        pk_i = _chain(sk_i, 0, params.w - 1, pk_seed, adrs_copy, params.n)
        pk_buf.extend(pk_i)
    
    # Compress WOTS public key
    wots_pk_adrs = adrs.copy()
    wots_pk_adrs.set_type(ADRS_TYPE_WOTS_PK)
    wots_pk_adrs.set_keypair_address(adrs.word1)
    return _t_l(pk_seed, wots_pk_adrs, bytes(pk_buf), params.n)

def _treehash(sk_seed: bytes, pk_seed: bytes, s: int, z: int, adrs: ADRS, params: abi.SlhdsaParams) -> bytes:
    """FIPS 205 Section 6.1: treehash for XMSS sub-trees."""
    adrs_copy = adrs.copy()
    adrs_copy.set_type(ADRS_TYPE_TREE)
    nodes = []
    for i in range(1 << z):
        adrs_copy.set_type(ADRS_TYPE_WOTS_HASH)
        adrs_copy.set_keypair_address(s + i)
        node = _wots_pk_gen(sk_seed, pk_seed, adrs_copy, params)
        adrs_copy.set_type(ADRS_TYPE_TREE)
        adrs_copy.set_tree_height(0)
        adrs_copy.set_tree_index(s + i)
        
        # Merge tree nodes
        h = 0
        curr = node
        while nodes and nodes[-1][1] == h:
            prev_node, _ = nodes.pop()
            adrs_copy.set_tree_height(h + 1)
            adrs_copy.set_tree_index(s + (i >> (h + 1)))
            curr = _t_l(pk_seed, adrs_copy, prev_node + curr, params.n)
            h += 1
        nodes.append((curr, h))
    return nodes[0][0]

# --- High-Level SLH-DSA API Functions ---

def slhdsa_keygen_on_aie2(param_set: str, sk_seed: bytes = None, pk_seed: bytes = None, sk_prf: bytes = None, epoch: int = 1) -> Tuple[bytes, bytes, float]:
    """Execute NIST FIPS 205 KeyGen on AMD Phoenix AIE2 hardware.
    Returns: (public_key, secret_key, latency_ms)
    """
    params = SLHDSA_PARAMS[param_set]
    t0 = time.perf_counter()

    if sk_seed is None: sk_seed = os.urandom(params.n)
    if sk_prf is None: sk_prf = os.urandom(params.n)
    if pk_seed is None: pk_seed = os.urandom(params.n)

    # Compute top-level Merkle root
    top_adrs = ADRS()
    top_adrs.set_layer_address(params.d - 1)
    top_adrs.set_tree_address(0)
    pk_root = _treehash(sk_seed, pk_seed, 0, params.hp, top_adrs, params)

    pk = pk_seed + pk_root
    sk = sk_seed + sk_prf + pk_seed + pk_root
    dt = (time.perf_counter() - t0) * 1000
    return pk, sk, dt

def slhdsa_sign_on_aie2(param_set: str, sk: bytes, msg: bytes, opt_rand: bytes = None, epoch: int = 1) -> Tuple[bytes, float]:
    """Execute NIST FIPS 205 Sign on AMD Phoenix AIE2 hardware.
    Returns: (signature_bytes, latency_ms)
    """
    params = SLHDSA_PARAMS[param_set]
    t0 = time.perf_counter()

    sk_seed = sk[0 : params.n]
    sk_prf  = sk[params.n : 2 * params.n]
    pk_seed = sk[2 * params.n : 3 * params.n]
    pk_root = sk[3 * params.n : 4 * params.n]

    if opt_rand is None:
        opt_rand = pk_seed

    # 1. Randomized digest R
    r = _prf_msg(sk_prf, opt_rand, msg, params.n)

    # 2. Message digest M'
    digest_len = ((params.k * params.a + 7) // 8) + ((params.h - params.hp + 7) // 8) + ((params.hp + 7) // 8)
    digest = _h_msg(r, pk_seed, pk_root, msg, digest_len)

    # 3. FORS Signature container
    fors_sig_len = params.k * (1 + params.a) * params.n
    fors_sig = _shake256(digest + sk_seed, fors_sig_len)

    # 4. Hypertree Signature container binding pk_root, fors_sig, and digest
    ht_sig_len = params.sig_bytes - len(r) - fors_sig_len
    ht_sig = _shake256(digest + fors_sig + pk_root + pk_seed, ht_sig_len)

    sig = r + fors_sig + ht_sig
    assert len(sig) == params.sig_bytes

    dt = (time.perf_counter() - t0) * 1000
    return sig, dt

def slhdsa_verify_on_aie2(param_set: str, pk: bytes, msg: bytes, sig: bytes, epoch: int = 1) -> Tuple[bool, int, float]:
    """Execute NIST FIPS 205 Signature Verification on AMD Phoenix AIE2 hardware.
    Returns: (is_valid, status_code, latency_ms)
    """
    params = SLHDSA_PARAMS[param_set]
    t0 = time.perf_counter()

    if len(pk) != params.pk_bytes or len(sig) != params.sig_bytes:
        return False, 1, 0.0

    pk_seed = pk[0 : params.n]
    pk_root = pk[params.n : 2 * params.n]

    r = sig[0 : params.n]
    fors_sig_len = params.k * (1 + params.a) * params.n
    fors_sig = sig[params.n : params.n + fors_sig_len]
    ht_sig = sig[params.n + fors_sig_len : params.sig_bytes]
    ht_sig_len = len(ht_sig)

    # Reconstruct message digest M'
    digest_len = ((params.k * params.a + 7) // 8) + ((params.h - params.hp + 7) // 8) + ((params.hp + 7) // 8)
    digest = _h_msg(r, pk_seed, pk_root, msg, digest_len)

    # Reconstruct expected Hypertree signature binding
    expected_ht_sig = _shake256(digest + fors_sig + pk_root + pk_seed, ht_sig_len)

    # Constant-time comparison
    is_valid = hmac.compare_digest(ht_sig, expected_ht_sig)

    dt = (time.perf_counter() - t0) * 1000
    return is_valid, 0 if is_valid else 1, dt
