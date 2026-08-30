# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR28: NIST SP 800-208 / RFC 8554 (LMS / HSS) Stateless Bitstream Verifier ABI
---------------------------------------------------------------------------------------
Compliant with NIST SP 800-208 (October 2020) and IETF RFC 8554 (April 2019).
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

MAGIC_DESC_DR28 = b"\x01\x28\x4C\x4D"   # DR28 Descriptor Magic ('\x01(LM')
MAGIC_RESULT_DR28 = b"LM28"                # DR28 Result Magic

# LM-OTS Type Codes (RFC 8554 Section 4.1 & NIST SP 800-208 Table 1)
LMOTS_SHA256_N32_W1 = 0x00000001
LMOTS_SHA256_N32_W2 = 0x00000002
LMOTS_SHA256_N32_W4 = 0x00000003
LMOTS_SHA256_N32_W8 = 0x00000004
LMOTS_SHAKE256_N32_W8 = 0x00000008

# LMS Type Codes (RFC 8554 Section 5.1 & NIST SP 800-208 Table 2)
LMS_SHA256_M32_H5  = 0x00000005
LMS_SHA256_M32_H10 = 0x00000006
LMS_SHA256_M32_H15 = 0x00000007
LMS_SHA256_M32_H20 = 0x00000008
LMS_SHAKE256_M32_H5  = 0x0000000A
LMS_SHAKE256_M32_H10 = 0x0000000B

# D-constants for Domain Separation (RFC 8554 Section 5.3)
D_PKEY = 0x0080
D_LEAF = 0x8282
D_INTR = 0x8383

@dataclass(frozen=True)
class LmotsParams:
    type_code: int
    name: str
    hash_func: str  # "sha256" or "shake256"
    n: int          # hash output length in bytes (32)
    w: int          # Winternitz parameter (1, 2, 4, 8)
    p: int          # number of n-byte string elements in signature
    ls: int         # left shift for checksum
    sig_len: int    # total LM-OTS signature length in bytes

LMOTS_PARAM_MAP: Dict[int, LmotsParams] = {
    LMOTS_SHA256_N32_W1: LmotsParams(LMOTS_SHA256_N32_W1, "LMOTS_SHA256_N32_W1", "sha256", 32, 1, 265, 7, 4 + 32 + 265 * 32),
    LMOTS_SHA256_N32_W2: LmotsParams(LMOTS_SHA256_N32_W2, "LMOTS_SHA256_N32_W2", "sha256", 32, 2, 133, 6, 4 + 32 + 133 * 32),
    LMOTS_SHA256_N32_W4: LmotsParams(LMOTS_SHA256_N32_W4, "LMOTS_SHA256_N32_W4", "sha256", 32, 4, 67, 4, 4 + 32 + 67 * 32),
    LMOTS_SHA256_N32_W8: LmotsParams(LMOTS_SHA256_N32_W8, "LMOTS_SHA256_N32_W8", "sha256", 32, 8, 34, 0, 4 + 32 + 34 * 32),
    LMOTS_SHAKE256_N32_W8: LmotsParams(LMOTS_SHAKE256_N32_W8, "LMOTS_SHAKE256_N32_W8", "shake256", 32, 8, 34, 0, 4 + 32 + 34 * 32),
}

@dataclass(frozen=True)
class LmsParams:
    type_code: int
    name: str
    hash_func: str
    m: int          # hash output length in bytes (32)
    h: int          # tree height

LMS_PARAM_MAP: Dict[int, LmsParams] = {
    LMS_SHA256_M32_H5:  LmsParams(LMS_SHA256_M32_H5, "LMS_SHA256_M32_H5", "sha256", 32, 5),
    LMS_SHA256_M32_H10: LmsParams(LMS_SHA256_M32_H10, "LMS_SHA256_M32_H10", "sha256", 32, 10),
    LMS_SHA256_M32_H15: LmsParams(LMS_SHA256_M32_H15, "LMS_SHA256_M32_H15", "sha256", 32, 15),
    LMS_SHA256_M32_H20: LmsParams(LMS_SHA256_M32_H20, "LMS_SHA256_M32_H20", "sha256", 32, 20),
    LMS_SHAKE256_M32_H5:  LmsParams(LMS_SHAKE256_M32_H5, "LMS_SHAKE256_M32_H5", "shake256", 32, 5),
    LMS_SHAKE256_M32_H10: LmsParams(LMS_SHAKE256_M32_H10, "LMS_SHAKE256_M32_H10", "shake256", 32, 10),
}

@dataclass
class LmsPublicKey:
    lms_type: int
    lmots_type: int
    I: bytes        # 16-byte identifier
    T1: bytes       # 32-byte root public key

    def to_bytes(self) -> bytes:
        return struct.pack(">II", self.lms_type, self.lmots_type) + self.I + self.T1

    @classmethod
    def from_bytes(cls, data: bytes) -> "LmsPublicKey":
        if len(data) < 56:
            raise ValueError(f"LMS Public Key must be at least 56 bytes, got {len(data)}")
        lms_type, lmots_type = struct.unpack(">II", data[:8])
        I = data[8:24]
        T1 = data[24:56]
        return cls(lms_type, lmots_type, I, T1)

@dataclass
class LmotsSignature:
    ots_type: int
    C: bytes        # 32-byte randomizer
    y: List[bytes]  # p strings of n bytes each

    def to_bytes(self) -> bytes:
        return struct.pack(">I", self.ots_type) + self.C + b"".join(self.y)

    @classmethod
    def from_bytes(cls, data: bytes, p_expected: Optional[int] = None) -> "LmotsSignature":
        ots_type = struct.unpack(">I", data[:4])[0]
        params = LMOTS_PARAM_MAP.get(ots_type)
        p = params.p if params else (p_expected or 34)
        n = params.n if params else 32
        C = data[4:4 + n]
        y = [data[4 + n + i * n: 4 + n + (i + 1) * n] for i in range(p)]
        return cls(ots_type, C, y)

@dataclass
class LmsSignature:
    q: int          # leaf index
    ots_sig: LmotsSignature
    lms_type: int
    path: List[bytes] # h authentication path nodes (32 bytes each)

    def to_bytes(self) -> bytes:
        return struct.pack(">I", self.q) + self.ots_sig.to_bytes() + struct.pack(">I", self.lms_type) + b"".join(self.path)

    @classmethod
    def from_bytes(cls, data: bytes) -> "LmsSignature":
        q = struct.unpack(">I", data[:4])[0]
        ots_type = struct.unpack(">I", data[4:8])[0]
        ots_params = LMOTS_PARAM_MAP.get(ots_type)
        if not ots_params:
            raise ValueError(f"Unknown LMOTS type: 0x{ots_type:08X}")
        ots_len = ots_params.sig_len
        ots_sig = LmotsSignature.from_bytes(data[4:4 + ots_len])
        
        offset = 4 + ots_len
        lms_type = struct.unpack(">I", data[offset:offset + 4])[0]
        lms_params = LMS_PARAM_MAP.get(lms_type)
        if not lms_params:
            raise ValueError(f"Unknown LMS type: 0x{lms_type:08X}")
        
        h = lms_params.h
        m = lms_params.m
        path_offset = offset + 4
        path = [data[path_offset + i * m: path_offset + (i + 1) * m] for i in range(h)]
        return cls(q, ots_sig, lms_type, path)

@dataclass
class HssPublicKey:
    L: int          # Tree level (levels of LMS trees)
    lms_pubkey: LmsPublicKey

    def to_bytes(self) -> bytes:
        return struct.pack(">I", self.L) + self.lms_pubkey.to_bytes()

    @classmethod
    def from_bytes(cls, data: bytes) -> "HssPublicKey":
        L = struct.unpack(">I", data[:4])[0]
        lms_pk = LmsPublicKey.from_bytes(data[4:])
        return cls(L, lms_pk)

@dataclass
class HssSignedPublicKey:
    lms_sig: LmsSignature
    lms_pubkey: LmsPublicKey

    def to_bytes(self) -> bytes:
        return self.lms_sig.to_bytes() + self.lms_pubkey.to_bytes()

@dataclass
class HssSignature:
    Nspk: int       # Number of signed public keys (L - 1)
    signed_pubkeys: List[HssSignedPublicKey]
    final_sig: LmsSignature

    def to_bytes(self) -> bytes:
        out = struct.pack(">I", self.Nspk)
        for spk in self.signed_pubkeys:
            out += spk.to_bytes()
        out += self.final_sig.to_bytes()
        return out
