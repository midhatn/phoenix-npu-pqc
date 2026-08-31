# SPDX-License-Identifier: Apache-2.0
"""Host unit tests for DR7 (ML-KEM-512 ML-KEM.Decaps)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import unittest
import zlib

from phoenix_sdr_dsp.pqc import dr7_mlkem512_decaps_abi as abi
from tests.pqc_device_resident.dr7_reference import mlkem512_decaps_reference

VECTORS_PATH = Path(__file__).parent / "data" / "dr7_nist_acvp_mlkem512_decaps_25.json"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    tc_id: str
    numeric_id: int
    dk: bytes
    c: bytes
    expected_k: bytes
    request_id: int


_DATA = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
PRE_SILICON_CORPUS = tuple(
    CorpusCase(
        label=case["tc_id"],
        tc_id=case["tc_id"],
        numeric_id=idx + 1,
        dk=bytes.fromhex(case["dk"]),
        c=bytes.fromhex(case["c"]),
        expected_k=bytes.fromhex(case["k"]),
        request_id=0xD7000000 + (idx + 1),
    )
    for idx, case in enumerate(_DATA["cases"])
)
ACVP_EXPECTED = {case.tc_id: case.expected_k for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 25


class DR7ReferenceTests(unittest.TestCase):
    def test_dr7_abi_contract(self) -> None:
        desc, req = abi.validate_request(b"\x00" * 1632, b"\x01" * 768, request_id=42)
        self.assertEqual(len(desc), 16)
        self.assertEqual(len(req), 2400)
        self.assertEqual(desc[0], 1)
        self.assertEqual(desc[1], 0x71)
        self.assertEqual(desc[2], 0x52)

        # Fake result unpacking
        k = b"\x42" * 32
        crc = zlib.crc32(k)
        header = struct.pack("<IIIII", abi.RESULT_MAGIC, 42, abi.STATUS_OK, 32, crc)
        unpacked = abi.unpack_result(header + k, expected_request_id=42)
        self.assertEqual(unpacked, k)

    def test_dr7_reference_acvp_all_25(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 25)
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                act_k = mlkem512_decaps_reference(case.dk, case.c)
                self.assertEqual(act_k, case.expected_k)


if __name__ == "__main__":
    unittest.main()
