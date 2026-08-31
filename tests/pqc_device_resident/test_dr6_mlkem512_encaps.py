# SPDX-License-Identifier: Apache-2.0
"""Host reference and contract validation test for Milestone DR6 (ML-KEM-512 ML-KEM.Encaps)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

from phoenix_sdr_dsp.pqc import dr6_mlkem512_encaps_abi as abi
from tests.pqc_device_resident.dr6_reference import mlkem512_encaps_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr6_nist_acvp_mlkem512_encaps_25.json"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    tc_id: int
    ek: bytes
    m: bytes
    expected_c: bytes
    expected_k: bytes
    request_id: int


_DATA = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
PRE_SILICON_CORPUS = tuple(
    CorpusCase(
        label=f"acvp-tcId-{case['tcId']:02d}",
        tc_id=case["tcId"],
        ek=bytes.fromhex(case["ek"]),
        m=bytes.fromhex(case["m"]),
        expected_c=bytes.fromhex(case["c"]),
        expected_k=bytes.fromhex(case["k"]),
        request_id=0xD6000000 + case["tcId"],
    )
    for case in _DATA["cases"]
)
ACVP_EXPECTED = {case.tc_id: (case.expected_c, case.expected_k) for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 25


class DR6ReferenceTests(unittest.TestCase):
    def test_dr6_abi_contract(self) -> None:
        ek_dummy = bytes(800)
        m_dummy = bytes(32)
        desc, req = abi.validate_request(ek_dummy, m_dummy, request_id=61)
        self.assertEqual(len(desc), abi.DESCRIPTOR_BYTES)
        self.assertEqual(len(req), abi.REQUEST_PAYLOAD_BYTES)

    def test_dr6_reference_acvp_all_25(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 25)
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                actual_c, actual_k = mlkem512_encaps_reference(case.ek, case.m)
                self.assertEqual(actual_c, case.expected_c)
                self.assertEqual(actual_k, case.expected_k)


if __name__ == "__main__":
    unittest.main()
