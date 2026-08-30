# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR37: ETSI TS 103 744 & BSI TR-02102-1 Dual-Scheme Hybrid KEM Engine ABI
----------------------------------------------------------------------------------
Standard packet descriptors and dataclasses for X25519MLKEM768 and SecP384R1MLKEM1024.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass
from typing import Tuple, Optional

MAGIC_DESC_DR37 = b"\x01\x37\x4B\x45"  # DR37 Descriptor Magic ('\x017KE')
MAGIC_RESULT_DR37 = b"KE37"              # DR37 Result Magic

PROFILE_X25519_MLKEM768       = 1
PROFILE_SECP384R1_MLKEM1024   = 2

@dataclass
class HybridKemKeyPair:
    profile_id: int
    classical_pk: bytes
    classical_sk: bytes
    pqc_pk: bytes
    pqc_sk: bytes

    def public_key_bytes(self) -> bytes:
        return self.classical_pk + self.pqc_pk

@dataclass
class HybridCiphertext:
    profile_id: int
    classical_ct: bytes
    pqc_ct: bytes

    def to_bytes(self) -> bytes:
        return self.classical_ct + self.pqc_ct

@dataclass
class HybridSharedSecret:
    profile_id: int
    shared_secret: bytes  # 32 bytes (256-bit quantum-safe key)
