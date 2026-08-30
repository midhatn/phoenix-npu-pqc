# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR42: ANSSI Composite & Dual-Signature Sovereign Standard Engine ABI
------------------------------------------------------------------------------
Compound signatures, dual public/private keys, and atomic verification verdicts.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import enum
import struct
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

MAGIC_DESC_DR42 = b"\x01\x42\x43\x53"  # DR42 Descriptor Magic ('\x01BCS')
MAGIC_RESULT_DR42 = b"CS42"              # DR42 Result Magic

class CompositeSignatureType(enum.IntEnum):
    ED25519_MLDSA44 = 1
    ECDSA_P384_MLDSA65 = 2
    ECDSA_P521_MLDSA87 = 3

@dataclass
class CompositePublicKey:
    sig_type: CompositeSignatureType
    pk_trad: bytes
    pk_pqc: bytes

    def to_bytes(self) -> bytes:
        header = struct.pack(">BII", int(self.sig_type), len(self.pk_trad), len(self.pk_pqc))
        return header + self.pk_trad + self.pk_pqc

    @classmethod
    def from_bytes(cls, data: bytes) -> "CompositePublicKey":
        sig_type_int, len_trad, len_pqc = struct.unpack(">BII", data[:9])
        pk_trad = data[9 : 9 + len_trad]
        pk_pqc = data[9 + len_trad : 9 + len_trad + len_pqc]
        return cls(CompositeSignatureType(sig_type_int), pk_trad, pk_pqc)

@dataclass
class CompositeSecretKey:
    sig_type: CompositeSignatureType
    sk_trad: bytes
    sk_pqc: bytes

    def to_bytes(self) -> bytes:
        header = struct.pack(">BII", int(self.sig_type), len(self.sk_trad), len(self.sk_pqc))
        return header + self.sk_trad + self.sk_pqc

    @classmethod
    def from_bytes(cls, data: bytes) -> "CompositeSecretKey":
        sig_type_int, len_trad, len_pqc = struct.unpack(">BII", data[:9])
        sk_trad = data[9 : 9 + len_trad]
        sk_pqc = data[9 + len_trad : 9 + len_trad + len_pqc]
        return cls(CompositeSignatureType(sig_type_int), sk_trad, sk_pqc)

@dataclass
class CompositeSignature:
    sig_type: CompositeSignatureType
    sig_trad: bytes
    sig_pqc: bytes

    def to_bytes(self) -> bytes:
        header = struct.pack(">BII", int(self.sig_type), len(self.sig_trad), len(self.sig_pqc))
        return header + self.sig_trad + self.sig_pqc

    @classmethod
    def from_bytes(cls, data: bytes) -> "CompositeSignature":
        sig_type_int, len_trad, len_pqc = struct.unpack(">BII", data[:9])
        sig_trad = data[9 : 9 + len_trad]
        sig_pqc = data[9 + len_trad : 9 + len_trad + len_pqc]
        return cls(CompositeSignatureType(sig_type_int), sig_trad, sig_pqc)

@dataclass
class CompositeVerifyResult:
    is_valid: bool
    trad_valid: bool
    pqc_valid: bool
    details: str = ""
