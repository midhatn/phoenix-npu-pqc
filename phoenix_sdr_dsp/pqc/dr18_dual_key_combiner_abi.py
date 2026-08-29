# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR18: NIST SP 800-56C Rev. 2 / SP 800-227 On-Device Dual-Key Combiner ABI
-----------------------------------------------------------------------------------
Compliant with NIST SP 800-56C Rev. 2, NIST SP 800-227, and BSI TR-02102.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
"""

import struct
import uuid
from typing import Tuple

MAGIC_DESC_DR18 = b"\x01\x71\x52\x12"  # DR18 Descriptor Magic
MAGIC_RESULT_DR18 = b"KC18"                # DR18 Result Magic
CUSTOMIZATION_STRING = b"ETSI-QKD-PQC-COMBINER-SP800-56C"

def pack_combiner_input(
    k_qkd: bytes,
    k_pqc: bytes,
    key_id: uuid.UUID,
    epoch: int,
    custom_label: bytes = CUSTOMIZATION_STRING
) -> bytes:
    """Pack multi-key combiner payload for AIE2 Keccak tile.
    Input layout: K_QKD (32B) || K_PQC (32B) || Key_ID (16B) || Epoch (4B) || Custom_Label
    """
    buf = bytearray()
    buf.extend(k_qkd[:32].ljust(32, b"\x00"))
    buf.extend(k_pqc[:32].ljust(32, b"\x00"))
    buf.extend(key_id.bytes)
    buf.extend(epoch.to_bytes(4, "little"))
    buf.extend(custom_label)
    return bytes(buf)
