# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR41: ETSI GS QKD 004 / 015 Quantum Key Management System (Q-KMS) ABI
-------------------------------------------------------------------------------
Standard ETSI 004/015 packet descriptors, FSM states, and dataclasses.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import enum
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

MAGIC_DESC_DR41 = b"\x01\x41\x51\x4B"  # DR41 Descriptor Magic ('\x01AQK')
MAGIC_RESULT_DR41 = b"QK41"              # DR41 Result Magic

class QkmsKeyStatus(enum.IntEnum):
    RESERVOIR_INGRESS = 1
    ALLOCATED_ACTIVE = 2
    SUSPENDED = 3
    EXPIRED = 4
    ZEROIZED = 5

@dataclass
class QkmsKeyDescriptor:
    key_id: str
    status: QkmsKeyStatus
    created_time: float
    ttl_seconds: float
    key_bytes: bytes
    source_sae: str
    dest_sae: str
    tenant_domain: str = "default"

    def is_expired(self, current_time: float) -> bool:
        return (current_time - self.created_time) > self.ttl_seconds

    def zeroize(self):
        self.key_bytes = b"\x00" * len(self.key_bytes)
        self.status = QkmsKeyStatus.ZEROIZED

@dataclass
class QkmsOpenSessionRequest:
    source_sae_id: str
    destination_sae_id: str
    qos_priority: int = 1
    key_size_bits: int = 256
    tenant_domain: str = "default"

@dataclass
class QkmsOpenSessionResponse:
    status: str
    key_stream_id: str
    max_key_count: int = 1024

@dataclass
class QkmsGetKeyResponse:
    status: str
    keys: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class QkmsRelayEnvelope:
    relay_id: str
    hop_source: str
    hop_target: str
    pqc_ciphertext: bytes
    otp_ciphertext: bytes
    target_key_id: str
