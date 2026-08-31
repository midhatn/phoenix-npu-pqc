# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and contract validation for DR10 (Sealed Lifecycle & Key Sources)."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import unittest

from phoenix_sdr_dsp.pqc import dr10_sealed_lifecycle_abi as abi


@dataclass(frozen=True)
class DR10Case:
    name: str
    numeric_id: int
    req_buf: bytes
    desc_buf: bytes
    expected_status: int
    expected_active: int
    request_id: int


def compute_ref_sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()


def _build_corpus() -> tuple[DR10Case, ...]:
    cases: list[DR10Case] = []

    # 1. Raw Ingress Conditioning (10 cases)
    for i in range(1, 11):
        entropy = bytes([(i * 17 + j) % 256 for j in range(64)])
        domain = (i % 6) + 1
        epoch = 100 + i
        req_buf = bytearray(256)
        req_buf[:64] = entropy
        desc_buf = abi.pack_dr10_descriptor(abi.SOURCE_MODE_RAW_INGRESS, domain, request_id=i, epoch=epoch)
        cases.append(
            DR10Case(
                name=f"dr10_raw_ingress_domain_{domain}_ep_{epoch}",
                numeric_id=len(cases) + 1,
                req_buf=bytes(req_buf),
                desc_buf=desc_buf,
                expected_status=0,
                expected_active=1,
                request_id=i,
            )
        )

    # 2. Authenticated External / QKD Ingress (Valid, 10 cases)
    for i in range(1, 11):
        key = bytes([(i * 31 + j) % 256 for j in range(64)])
        source_id = f"QKD_NODE_{i:02d}".encode()
        domain = (i % 6) + 1
        epoch = 200 + i

        header = bytearray(32)
        header[0:4] = b"QKD1"
        header[4:8] = epoch.to_bytes(4, "little")
        header[8] = domain
        header[16:32] = source_id.ljust(16, b"\x00")[:16]

        raw_to_sign = bytes(header) + key
        tag = compute_ref_sha3_256(raw_to_sign)

        req_buf = bytearray(256)
        req_buf[0:32] = header
        req_buf[32:96] = key
        req_buf[96:128] = tag

        desc_buf = abi.pack_dr10_descriptor(abi.SOURCE_MODE_AUTH_QKD_INGRESS, domain, request_id=20 + i, epoch=epoch)
        cases.append(
            DR10Case(
                name=f"dr10_auth_qkd_valid_node_{i}_domain_{domain}",
                numeric_id=len(cases) + 1,
                req_buf=bytes(req_buf),
                desc_buf=desc_buf,
                expected_status=0,
                expected_active=1,
                request_id=20 + i,
            )
        )

    # 3. Authenticated External / QKD Ingress (Invalid Tag / Rejection, 5 cases)
    for i in range(1, 6):
        key = bytes([0xAA] * 64)
        source_id = b"ROGUE_NODE"
        domain = 1
        epoch = 300 + i
        header = bytearray(32)
        header[0:4] = b"QKD1"
        header[4:8] = epoch.to_bytes(4, "little")
        header[8] = domain
        header[16:32] = source_id.ljust(16, b"\x00")[:16]

        tag = bytes([0xFF] * 32)
        req_buf = bytearray(256)
        req_buf[0:32] = header
        req_buf[32:96] = key
        req_buf[96:128] = tag

        desc_buf = abi.pack_dr10_descriptor(abi.SOURCE_MODE_AUTH_QKD_INGRESS, domain, request_id=40 + i, epoch=epoch)
        cases.append(
            DR10Case(
                name=f"dr10_auth_qkd_invalid_tag_rej_{i}",
                numeric_id=len(cases) + 1,
                req_buf=bytes(req_buf),
                desc_buf=desc_buf,
                expected_status=3,  # kBadAuthTag
                expected_active=0,
                request_id=40 + i,
            )
        )

    # 4. Authenticated External / QKD Ingress (Domain Mismatch, 5 cases)
    for i in range(1, 6):
        key = bytes([0xBB] * 64)
        source_id = b"QKD_NODE_MIS"
        req_domain = 1
        desc_domain = 2  # Mismatch
        epoch = 400 + i
        header = bytearray(32)
        header[0:4] = b"QKD1"
        header[4:8] = epoch.to_bytes(4, "little")
        header[8] = req_domain
        header[16:32] = source_id.ljust(16, b"\x00")[:16]

        raw_to_sign = bytes(header) + key
        tag = compute_ref_sha3_256(raw_to_sign)
        req_buf = bytearray(256)
        req_buf[0:32] = header
        req_buf[32:96] = key
        req_buf[96:128] = tag

        desc_buf = abi.pack_dr10_descriptor(abi.SOURCE_MODE_AUTH_QKD_INGRESS, desc_domain, request_id=50 + i, epoch=epoch)
        cases.append(
            DR10Case(
                name=f"dr10_auth_qkd_domain_mismatch_rej_{i}",
                numeric_id=len(cases) + 1,
                req_buf=bytes(req_buf),
                desc_buf=desc_buf,
                expected_status=4,  # kDomainMismatch
                expected_active=0,
                request_id=50 + i,
            )
        )

    # 5. Authenticated External / QKD Ingress (Stale Epoch, 5 cases)
    for i in range(1, 6):
        key = bytes([0xCC] * 64)
        source_id = b"QKD_NODE_STALE"
        domain = 1
        req_epoch = 100  # Stale
        desc_epoch = 500  # Expected >= 500
        header = bytearray(32)
        header[0:4] = b"QKD1"
        header[4:8] = req_epoch.to_bytes(4, "little")
        header[8] = domain
        header[16:32] = source_id.ljust(16, b"\x00")[:16]

        raw_to_sign = bytes(header) + key
        tag = compute_ref_sha3_256(raw_to_sign)
        req_buf = bytearray(256)
        req_buf[0:32] = header
        req_buf[32:96] = key
        req_buf[96:128] = tag

        desc_buf = abi.pack_dr10_descriptor(abi.SOURCE_MODE_AUTH_QKD_INGRESS, domain, request_id=60 + i, epoch=desc_epoch)
        cases.append(
            DR10Case(
                name=f"dr10_auth_qkd_stale_epoch_rej_{i}",
                numeric_id=len(cases) + 1,
                req_buf=bytes(req_buf),
                desc_buf=desc_buf,
                expected_status=5,  # kEpochStale
                expected_active=0,
                request_id=60 + i,
            )
        )

    # 6. Sealed Session Teardown & Zeroization (5 cases)
    for i in range(1, 6):
        domain = 1
        req_buf = bytes(256)
        desc_buf = abi.pack_dr10_descriptor(abi.SOURCE_MODE_SEALED_SESSION, domain, request_id=70 + i, epoch=600)
        cases.append(
            DR10Case(
                name=f"dr10_sealed_teardown_zeroize_{i}",
                numeric_id=len(cases) + 1,
                req_buf=req_buf,
                desc_buf=desc_buf,
                expected_status=0,
                expected_active=0,
                request_id=70 + i,
            )
        )

    return tuple(cases)


PRE_SILICON_CORPUS = _build_corpus()
EXPECTED_RESULTS = {case.name: (case.expected_status, case.expected_active) for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 40


class DR10ReferenceTests(unittest.TestCase):
    def test_dr10_corpus_count(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 40)

    def test_dr10_abi_contract(self) -> None:
        desc = abi.pack_dr10_descriptor(abi.SOURCE_MODE_RAW_INGRESS, 1, request_id=1, epoch=100)
        self.assertEqual(len(desc), 16)
        self.assertEqual(desc[0:4], abi.MAGIC_DESC_DR10)
        self.assertEqual(desc[4], abi.SOURCE_MODE_RAW_INGRESS)
        self.assertEqual(desc[5], 1)
        self.assertEqual(desc[6], 10)


if __name__ == "__main__":
    unittest.main()
