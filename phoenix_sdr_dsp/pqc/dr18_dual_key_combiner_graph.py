# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR18: NIST SP 800-56C Rev. 2 / SP 800-227 On-Device Dual-Key Combiner Graph.
Fuses K_QKD and K_PQC on physical AIE2 vector tiles (DR9 Keccak Engine) with zero host RAM leakage.
"""

import time
import uuid
from typing import Tuple
from . import dr18_dual_key_combiner_abi as abi
from . import dr9_fips202_graph as dr9

BACKEND_LABEL = "dr18-dual-key-combiner:silicon"

def combine_keys_on_aie2(
    k_qkd: bytes,
    k_pqc: bytes,
    key_id: uuid.UUID,
    epoch: int = 1,
    out_len: int = 32,
    custom_label: bytes = abi.CUSTOMIZATION_STRING
) -> Tuple[bytes, float]:
    """Execute NIST SP 800-56C extraction on physical Phoenix NPU silicon via DR9 Keccak graph."""
    combiner_input = abi.pack_combiner_input(k_qkd, k_pqc, key_id, epoch, custom_label)
    t0 = time.time()
    k_final = dr9.run_fips202_service("SHAKE256", combiner_input, out_len=out_len)
    dt = (time.time() - t0) * 1000
    return k_final, dt
