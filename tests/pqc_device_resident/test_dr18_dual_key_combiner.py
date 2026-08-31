# SPDX-License-Identifier: Apache-2.0
"""Host reference calculation for DR18 NIST SP 800-56C Dual-Key Combiner."""
from __future__ import annotations

from hashlib import shake_256
from pathlib import Path
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr18_dual_key_combiner_abi as abi


def compute_ref_k_final(
    k_qkd: bytes, k_pqc: bytes, key_id: uuid.UUID, epoch: int, out_len: int = 32
) -> bytes:
    """Host reference implementation of NIST SP 800-56C dual key combination."""
    inp = abi.pack_combiner_input(k_qkd, k_pqc, key_id, epoch)
    return shake_256(inp).digest(out_len)
