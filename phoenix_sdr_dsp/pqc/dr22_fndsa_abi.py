# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON) ABI Specification and Parameters.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
"""

from dataclasses import dataclass
import struct
from typing import Dict

MAGIC_DESC_DR22 = b"\x01\x22\x46\x4E"  # 0x01 0x22 'F' 'N'
MAGIC_RES_DR22  = 0x32324E46          # 'F' 'N' '2' '2' (Little-endian uint32: 0x32324E46)

Q_FNDSA = 12289

@dataclass(frozen=True)
class FndsaParams:
    name: str
    n: int
    log_n: int
    sigma: float
    sig_bound: int      # beta^2 bound
    pk_bytes: int       # Public key wire bytes (897 or 1793)
    sk_bytes: int       # Secret key wire bytes (1281 or 2305)
    sig_max_bytes: int  # Max signature size
    salt_bytes: int = 40

FNDSA_PARAMS: Dict[str, FndsaParams] = {
    "FN-DSA-512": FndsaParams(
        name="FN-DSA-512",
        n=512,
        log_n=9,
        sigma=165.736613401,
        sig_bound=34034726,
        pk_bytes=897,
        sk_bytes=1281,
        sig_max_bytes=690,
        salt_bytes=40,
    ),
    "FN-DSA-1024": FndsaParams(
        name="FN-DSA-1024",
        n=1024,
        log_n=10,
        sigma=168.388571447,
        sig_bound=70265242,
        pk_bytes=1793,
        sk_bytes=2305,
        sig_max_bytes=1330,
        salt_bytes=40,
    ),
}

def pack_fndsa_descriptor(
    param_set: str,
    operation_mode: int,  # 0 = KeyGen, 1 = Sign, 2 = Verify
    msg_len: int = 0,
    epoch: int = 1,
    sig_max_bytes: int = 0,
) -> bytes:
    """Pack a 32-byte descriptor for DR22 FN-DSA service."""
    if param_set not in FNDSA_PARAMS:
        raise ValueError(f"Unknown FN-DSA parameter set: {param_set}")
    p = FNDSA_PARAMS[param_set]
    mode_id = 0 if p.n == 512 else 1

    desc = bytearray(32)
    desc[0:4] = MAGIC_DESC_DR22
    desc[4] = mode_id
    desc[5] = operation_mode
    struct.pack_into("<H", desc, 6, p.n)
    struct.pack_into("<I", desc, 8, msg_len)
    struct.pack_into("<I", desc, 12, epoch)
    struct.pack_into("<I", desc, 16, p.sig_bound)
    struct.pack_into("<H", desc, 20, p.pk_bytes)
    struct.pack_into("<H", desc, 22, sig_max_bytes if sig_max_bytes > 0 else p.sig_max_bytes)
    return bytes(desc)
