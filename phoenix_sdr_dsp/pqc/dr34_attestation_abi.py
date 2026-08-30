# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR34: On-Device Firmware Remote Attestation & TPM 2.0 / TCG DICE Engine ABI
-------------------------------------------------------------------------------------
TCG DICE layered derivation, TPM 2.0 PCR register bank, and Quote payload structures.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

MAGIC_DESC_DR34 = b"\x01\x34\x44\x49"   # DR34 Descriptor Magic ('\x014DI')
MAGIC_RESULT_DR34 = b"DI34"                # DR34 Result Magic

PCR_BITSTREAM        = 12
PCR_SECURITY_VERSION = 14
PCR_CONFIG           = 15

@dataclass
class TpmPcrBank:
    pcrs: Dict[int, bytes] = field(default_factory=lambda: {i: b"\x00" * 32 for i in range(24)})

    def extend(self, pcr_idx: int, data: bytes) -> bytes:
        curr = self.pcrs.get(pcr_idx, b"\x00" * 32)
        h = hashlib.sha256(curr + data).digest()
        self.pcrs[pcr_idx] = h
        return h

    def get_composite_digest(self, pcr_list: List[int]) -> bytes:
        cat = b"".join(self.pcrs.get(idx, b"\x00" * 32) for idx in sorted(pcr_list))
        return hashlib.sha256(cat).digest()

@dataclass
class DiceLayerEvidence:
    layer: int
    cdi: bytes
    alias_pk: bytes
    security_version: int
    claims_digest: bytes

@dataclass
class TpmQuotePayload:
    pcr_selection: List[int]
    pcr_composite_digest: bytes
    qualifying_data: bytes  # external nonce
    aik_algorithm: str      # "ML-DSA-44" or "LMS"
    aik_public_key: bytes
    signature: bytes

@dataclass
class AttestationVerificationVerdict:
    is_valid: bool
    reason: str
    pcr_digest_matched: bool
    signature_valid: bool
    nonce_matched: bool
