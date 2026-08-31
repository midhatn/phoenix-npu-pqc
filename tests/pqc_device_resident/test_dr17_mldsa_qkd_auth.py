# SPDX-License-Identifier: Apache-2.0
"""Host reference and test vector generation for DR17 ML-DSA QKD Authentication."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import shake_256
from pathlib import Path
import secrets
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr17_mldsa_qkd_auth_abi as abi


@dataclass(frozen=True)
class DR17AuthCase:
    name: str
    param: str
    pk: bytes
    master: str
    slave: str
    key_id: uuid.UUID
    epoch: int
    nonce: bytes
    sig: bytes
    is_authentic: bool


def compute_mldsa65_mu(pk65: bytes, manifest: bytes) -> bytes:
    tr = shake_256(pk65).digest(64)
    return shake_256(tr + manifest).digest(64)
