# SPDX-License-Identifier: Apache-2.0
"""ABI definitions and descriptor structures for Milestone DR31:
NIST SP 800-208 / RFC 5280 / RFC 5652 X.509 Post-Quantum Certificates & Hybrid CMS Co-Processor.
"""
from __future__ import annotations

import struct
from typing import NamedTuple, Tuple, Dict, Any, Optional

MAGIC_DESC_DR31 = 0x01315843  # DR31 XC (X.509 / CMS Co-Processor magic)

# Algorithm Identifiers
ALGO_ML_DSA_44              = 1
ALGO_ML_DSA_65              = 2
ALGO_ML_DSA_87              = 3
ALGO_SLH_DSA_SHAKE_128S     = 4
ALGO_LMS_SHA256_M32_H10     = 5
ALGO_HYBRID_ED25519_MLDSA65 = 6
ALGO_ML_KEM_768             = 7
ALGO_ML_KEM_1024            = 8

# Hardware Operation Modes
MODE_X509_PQC_VERIFY         = 0  # Verify PQC certificate signature over TBS digest
MODE_X509_HYBRID_VERIFY      = 1  # Verify composite / hybrid certificate (dual classical + PQC)
MODE_CMS_SIGNED_DATA_VERIFY  = 2  # Verify CMS SignedData signer signature over signedAttrs
MODE_CMS_ENVELOPED_UNWRAP    = 3  # CMS EnvelopedData KEM decapsulation & CEK unwrapping
MODE_X509_CHAIN_STEP_VERIFY  = 4  # Intermediate CA to Leaf certificate validation step

# Flag definitions
FLAG_IS_CA                  = 0x0001
FLAG_HAS_SIGNED_ATTRS       = 0x0002
FLAG_KEY_USAGE_DIGITAL_SIG  = 0x0004
FLAG_KEY_USAGE_KEY_ENCIPHER = 0x0008

REQ_TOTAL_BYTES = 16384
DESC_TOTAL_BYTES = 32
RESULT_TOTAL_BYTES = 2048


class DR31Descriptor(NamedTuple):
    magic: int
    operation_mode: int
    algo_id: int
    flags: int
    tbs_len: int
    pk_len: int
    sig_len: int
    aux_len: int


def pack_dr31_descriptor(
    operation_mode: int,
    algo_id: int = ALGO_ML_DSA_65,
    flags: int = 0,
    tbs_len: int = 0,
    pk_len: int = 0,
    sig_len: int = 0,
    aux_len: int = 0,
) -> bytes:
    """Packs 32-byte hardware descriptor for DR31 X.509 / CMS processing."""
    desc = bytearray(32)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_DESC_DR31,
        int(operation_mode),
        int(algo_id),
        int(flags),
        int(tbs_len),
        int(pk_len),
        int(sig_len),
        int(aux_len),
    )
    return bytes(desc)


def unpack_dr31_descriptor(data: bytes) -> DR31Descriptor:
    """Unpacks 32-byte hardware descriptor for DR31."""
    if len(data) < 32:
        raise ValueError(f"DR31 descriptor requires 32 bytes, received {len(data)}")
    magic, op_mode, algo, flg, tbs_l, pk_l, sig_l, aux_l = struct.unpack_from("<IIIIIIII", data, 0)
    if magic != MAGIC_DESC_DR31:
        raise ValueError(f"Invalid DR31 magic: 0x{magic:08X} != 0x{MAGIC_DESC_DR31:08X}")
    return DR31Descriptor(
        magic=magic,
        operation_mode=op_mode,
        algo_id=algo,
        flags=flg,
        tbs_len=tbs_l,
        pk_len=pk_l,
        sig_len=sig_l,
        aux_len=aux_l,
    )


def pack_x509_verify_request(
    tbs_digest: bytes,
    public_key: bytes,
    signature: bytes,
    operation_mode: int = MODE_X509_PQC_VERIFY,
    algo_id: int = ALGO_ML_DSA_65,
    flags: int = 0,
    aux_data: bytes = b"",
) -> Tuple[bytes, bytes]:
    """Packs a 32-byte descriptor and a 16384-byte hardware request buffer."""
    if len(tbs_digest) > 64:
        raise ValueError(f"TBS digest exceeds 64 bytes: {len(tbs_digest)}")
    if len(public_key) > 3840:
        raise ValueError(f"Public key exceeds 3840 bytes: {len(public_key)}")
    if len(signature) > 10240:
        raise ValueError(f"Signature exceeds 10240 bytes: {len(signature)}")
    if len(aux_data) > 2048:
        raise ValueError(f"Aux data exceeds 2048 bytes: {len(aux_data)}")

    desc = pack_dr31_descriptor(
        operation_mode=operation_mode,
        algo_id=algo_id,
        flags=flags,
        tbs_len=len(tbs_digest),
        pk_len=len(public_key),
        sig_len=len(signature),
        aux_len=len(aux_data),
    )

    req = bytearray(REQ_TOTAL_BYTES)
    # Header: 32 bytes
    struct.pack_into(
        "<IIII",
        req,
        0,
        MAGIC_DESC_DR31,
        operation_mode,
        algo_id,
        flags,
    )
    # TBS digest at offset 32 (up to 64 bytes)
    req[32:32 + len(tbs_digest)] = tbs_digest

    # Public key at offset 256 (up to 3840 bytes)
    req[256:256 + len(public_key)] = public_key

    # Signature at offset 4096 (up to 10240 bytes)
    req[4096:4096 + len(signature)] = signature

    # Aux data at offset 14336 (up to 2048 bytes)
    if aux_data:
        req[14336:14336 + len(aux_data)] = aux_data

    return desc, bytes(req)
