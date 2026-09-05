# SPDX-License-Identifier: Apache-2.0
"""Milestone DR37: Dual-Scheme Hybrid KEM Engine ABI.
Defines descriptor structures, request/result packing, and independent reference oracle
for X25519 + ML-KEM-768 and SecP384R1 + ML-KEM-1024 hybrid key exchange on AMD Phoenix AIE2.
"""

import hashlib
import hmac
import struct
from typing import Tuple, Optional, Dict, Any

# Architectural Constants
MAGIC_HEADER = 0x454B3701   # "\x017KE"
MAGIC_RESULT = 0x3733454B   # "KE37"

# Operation Modes
MODE_HYBRID_ENCAPS_COMBINE = 1
MODE_HYBRID_DECAPS_COMBINE = 2
MODE_HYBRID_SPLIT_SECRET   = 3
MODE_HYBRID_POLICY_ENFORCE = 4
MODE_HYBRID_ZEROIZE        = 5

# Profile Identifiers
PROFILE_X25519_MLKEM768     = 1
PROFILE_SECP384R1_MLKEM1024 = 2

# Status Return Codes
STATUS_SUCCESS              = 0
STATUS_ERR_INVALID_MAGIC    = 1
STATUS_ERR_DEGENERATE_KEY   = 2
STATUS_ERR_POLICY_VIOLATION = 3
STATUS_ERR_INVALID_PROFILE  = 4
STATUS_ERR_INTEGRITY_FAIL   = 5

# Buffer Geometries (32-byte aligned for AIE2 ObjectFifo)
DESC_TOTAL_BYTES   = 64
REQ_TOTAL_BYTES    = 16384
RESULT_TOTAL_BYTES = 2048


def pack_dr37_descriptor(
    op_mode: int,
    profile_id: int = PROFILE_X25519_MLKEM768,
    ss_c_len: int = 32,
    ss_pqc_len: int = 32,
    ct_c_len: int = 32,
    ct_pqc_len: int = 1088,
    flags: int = 0,
    seq_id: int = 0,
) -> bytes:
    """Packs a 64-byte descriptor for DR37 Hybrid KEM dispatch."""
    desc = bytearray(DESC_TOTAL_BYTES)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_HEADER,
        op_mode,
        profile_id,
        ss_c_len,
        ss_pqc_len,
        ct_c_len,
        ct_pqc_len,
        flags,
    )
    struct.pack_into("<I", desc, 32, seq_id)
    return bytes(desc)


def pack_dr37_request(
    classical_ss: bytes,
    pqc_ss: bytes,
    classical_ct: bytes = b"",
    salt: bytes = b"",
    pqc_ct: bytes = b"",
) -> bytes:
    """Packs 16KB request tensor containing secrets, ciphertexts, and salt."""
    req = bytearray(REQ_TOTAL_BYTES)

    # Offsets:
    # 0..31: classical_ss (32 bytes)
    # 32..63: pqc_ss (32 bytes)
    # 64..95: classical_ct (32 bytes)
    # 96..127: salt (32 bytes)
    # 128..1215: pqc_ct (up to 1568 bytes)
    req[0 : len(classical_ss)] = classical_ss[:32]
    req[32 : 32 + len(pqc_ss)] = pqc_ss[:32]
    if classical_ct:
        req[64 : 64 + len(classical_ct)] = classical_ct[:32]
    if salt:
        req[96 : 96 + len(salt)] = salt[:32]
    if pqc_ct:
        req[128 : 128 + len(pqc_ct)] = pqc_ct

    return bytes(req)


def unpack_dr37_result(result_bytes: bytes) -> Dict[str, Any]:
    """Unpacks a 2KB result buffer returned by DR37 service kernel."""
    if len(result_bytes) < 160:
        raise ValueError(f"Result buffer too short: {len(result_bytes)} bytes")

    status, op_mode, outcome, cycle_est = struct.unpack_from("<IIII", result_bytes, 0)
    final_ss = bytes(result_bytes[16:48])
    enc_key = bytes(result_bytes[48:80])
    mac_key = bytes(result_bytes[80:112])
    derived_iv = bytes(result_bytes[112:128])
    transcript_digest = bytes(result_bytes[128:160])

    return {
        "status": status,
        "op_mode": op_mode,
        "verification_outcome": outcome,
        "cycle_estimate": cycle_est,
        "final_shared_secret": final_ss,
        "derived_enc_key": enc_key,
        "derived_mac_key": mac_key,
        "derived_iv": derived_iv,
        "transcript_binding_digest": transcript_digest,
    }


def hkdf_extract_and_expand_sha256(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """Independent reference HKDF (RFC 5869) using SHA-256."""
    if not salt:
        salt = bytes(32)
    # Step 1: Extract
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()

    # Step 2: Expand
    okm = bytearray()
    t = b""
    block_num = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([block_num]), hashlib.sha256).digest()
        okm.extend(t)
        block_num += 1

    return bytes(okm[:length])


def reference_dr37_oracle(request_bytes: bytes, descriptor_bytes: bytes) -> bytes:
    """[HOST REFERENCE] Independent normative oracle for DR37 Hybrid KEM combiner."""
    magic, op_mode, profile_id, ss_c_len, ss_pqc_len, ct_c_len, ct_pqc_len, flags = struct.unpack_from(
        "<IIIIIIII", descriptor_bytes, 0
    )

    result = bytearray(RESULT_TOTAL_BYTES)

    if magic != MAGIC_HEADER:
        struct.pack_into("<IIII", result, 0, STATUS_ERR_INVALID_MAGIC, op_mode, 0, 0)
        return bytes(result)

    if profile_id not in (PROFILE_X25519_MLKEM768, PROFILE_SECP384R1_MLKEM1024):
        struct.pack_into("<IIII", result, 0, STATUS_ERR_INVALID_PROFILE, op_mode, 0, 0)
        return bytes(result)

    classical_ss = bytes(request_bytes[0:32])
    pqc_ss = bytes(request_bytes[32:64])
    classical_ct = bytes(request_bytes[64:96])
    salt = bytes(request_bytes[96:128])
    pqc_ct = bytes(request_bytes[128 : 128 + ct_pqc_len])

    # Check for degenerate all-zero keys
    is_classical_zero = all(b == 0 for b in classical_ss)
    is_pqc_zero = all(b == 0 for b in pqc_ss)

    if op_mode in (MODE_HYBRID_ENCAPS_COMBINE, MODE_HYBRID_DECAPS_COMBINE, MODE_HYBRID_POLICY_ENFORCE):
        if is_classical_zero or is_pqc_zero:
            struct.pack_into("<IIII", result, 0, STATUS_ERR_DEGENERATE_KEY, op_mode, 0, 150)
            return bytes(result)

    if op_mode == MODE_HYBRID_ZEROIZE:
        # Zeroize mode: all outputs unconditionally 0
        struct.pack_into("<IIII", result, 0, STATUS_SUCCESS, op_mode, 1, 200)
        return bytes(result)

    # Compute transcript binding digest H(CT_c || H(CT_pqc))
    h_pqc_ct = hashlib.sha256(pqc_ct).digest()
    transcript_hasher = hashlib.sha256()
    transcript_hasher.update(classical_ct)
    transcript_hasher.update(h_pqc_ct)
    transcript_digest = transcript_hasher.digest()

    # Form IKM = classical_ss || pqc_ss (ETSI TS 103 744 & RFC 9180)
    ikm = classical_ss + pqc_ss
    info_prefix = b"ETSI_HYBRID_KEM_TS_103_744" + transcript_digest

    # Extract-and-Expand to 112 bytes: 32 (SS) + 32 (Enc) + 32 (Mac) + 16 (IV)
    derived_material = hkdf_extract_and_expand_sha256(salt, ikm, info_prefix, 112)

    final_ss = derived_material[0:32]
    enc_key = derived_material[32:64]
    mac_key = derived_material[64:96]
    derived_iv = derived_material[96:112]

    # Pack into result
    status = STATUS_SUCCESS
    outcome = 1
    cycle_est = 720 if profile_id == PROFILE_X25519_MLKEM768 else 950

    struct.pack_into("<IIII", result, 0, status, op_mode, outcome, cycle_est)
    result[16:48] = final_ss
    result[48:80] = enc_key
    result[80:112] = mac_key
    result[112:128] = derived_iv
    result[128:160] = transcript_digest

    return bytes(result)
