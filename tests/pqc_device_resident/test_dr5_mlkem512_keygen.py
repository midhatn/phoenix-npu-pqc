# SPDX-License-Identifier: Apache-2.0
"""Host reference and contract validation test for Milestone DR5 (ML-KEM-512 ML-KEM.KeyGen)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

from phoenix_sdr_dsp.pqc import dr5_mlkem512_keygen_abi as abi
from tests.pqc_device_resident.dr5_reference import mlkem512_keygen_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr5_nist_acvp_mlkem512_keygen_25.json"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    tc_id: int
    d: bytes
    z: bytes
    expected_ek: bytes
    expected_dk: bytes
    request_id: int


_DATA = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
PRE_SILICON_CORPUS = tuple(
    CorpusCase(
        label=f"acvp-tcId-{case['tcId']:02d}",
        tc_id=case["tcId"],
        d=bytes.fromhex(case["d"]),
        z=bytes.fromhex(case["z"]),
        expected_ek=bytes.fromhex(case["ek"]),
        expected_dk=bytes.fromhex(case["dk"]),
        request_id=0xD5000000 + case["tcId"],
    )
    for case in _DATA["cases"]
)
ACVP_EXPECTED = {case.tc_id: (case.expected_ek, case.expected_dk) for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 25


class DR5ReferenceTests(unittest.TestCase):
    def test_dr5_abi_contract(self) -> None:
        d_dummy = bytes(32)
        z_dummy = bytes(32)
        desc, req = abi.validate_request(d_dummy, z_dummy, request_id=51)
        self.assertEqual(len(desc), abi.DESCRIPTOR_BYTES)
        self.assertEqual(len(req), abi.REQUEST_PAYLOAD_BYTES)

    def test_dr5_reference_acvp_all_25(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 25)
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                actual_ek, actual_dk = mlkem512_keygen_reference(case.d, case.z)
                self.assertEqual(actual_ek, case.expected_ek)
                self.assertEqual(actual_dk, case.expected_dk)


if __name__ == "__main__":
    unittest.main()
