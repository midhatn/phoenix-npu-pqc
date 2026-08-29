# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR17: ML-DSA Asymmetric QKD Control Plane Authenticator ABI
---------------------------------------------------------------------
Compliant with NIST FIPS 204 (ML-DSA) & ETSI GS QKD 015 Security Framework.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
"""

import struct
import uuid
from typing import NamedTuple, Tuple

MAGIC_DESC_DR17 = b"\x01\x71\x52\x11"  # DR17 Descriptor Magic
MAGIC_RESULT_DR17 = b"QA17"                # DR17 Result Magic

# Status Codes
STATUS_AUTH_VALID = 0
STATUS_AUTH_INVALID_SIG = 1
STATUS_AUTH_TAMPERED_MANIFEST = 2
STATUS_AUTH_UNSUPPORTED_PARAM = 3

class QkdAuthToken(NamedTuple):
    sae_master_id: str
    sae_slave_id: str
    key_id: uuid.UUID
    epoch: int
    nonce: bytes
    param_set: str
    signature: bytes
    public_key: bytes

def pack_dr17_manifest(sae_master: str, sae_slave: str, key_id: uuid.UUID, epoch: int, nonce: bytes) -> bytes:
    """Pack authenticated QKD session manifest (64 bytes)."""
    # 0..15: key_id (UUID 16B)
    # 16..19: epoch (uint32)
    # 20..31: nonce (12B)
    # 32..47: sae_master (16B)
    # 48..63: sae_slave (16B)
    buf = bytearray(64)
    buf[0:16] = key_id.bytes
    buf[16:20] = epoch.to_bytes(4, "little")
    buf[20:32] = nonce.ljust(12, b"\x00")[:12]
    buf[32:48] = sae_master.encode("utf-8").ljust(16, b"\x00")[:16]
    buf[48:64] = sae_slave.encode("utf-8").ljust(16, b"\x00")[:16]
    return bytes(buf)
