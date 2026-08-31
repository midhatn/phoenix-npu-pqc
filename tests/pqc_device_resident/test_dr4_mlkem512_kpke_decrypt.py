# SPDX-License-Identifier: Apache-2.0
"""Host reference and contract validation test for Milestone DR4 (ML-KEM-512 K-PKE.Decrypt)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

from phoenix_sdr_dsp.pqc import dr4_mlkem512_kpke_decrypt_abi as abi
from tests.pqc_device_resident.dr4_reference import kpke_decrypt_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr4_nist_acvp_mlkem512_kpke_decrypt_25.json"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    tc_id: int
    dk_pke: bytes
    c: bytes
    expected_m: bytes
    request_id: int


_DATA = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
PRE_SILICON_CORPUS = tuple(
    CorpusCase(
        label=f"acvp-tcId-{case['tcId']:02d}",
        tc_id=case["tcId"],
        dk_pke=bytes.fromhex(case["dkPke"]),
        c=bytes.fromhex(case["c"]),
        expected_m=bytes.fromhex(case["m"]),
        request_id=0xD4000000 + case["tcId"],
    )
    for case in _DATA["cases"]
)
ACVP_EXPECTED = {case.tc_id: case.expected_m for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 25


class DR4ReferenceTests(unittest.TestCase):
    def test_dr4_abi_contract(self) -> None:
        dk_dummy = bytes(768)
        c_dummy = bytes(768)
        desc, req = abi.validate_request(dk_dummy, c_dummy, request_id=42)
        self.assertEqual(len(desc), abi.DESCRIPTOR_BYTES)
        self.assertEqual(len(req), abi.REQUEST_PAYLOAD_BYTES)

    def test_dr4_reference_acvp_all_25(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 25)
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                actual_m = kpke_decrypt_reference(case.dk_pke, case.c)
                self.assertEqual(actual_m, case.expected_m)


if __name__ == "__main__":
    unittest.main()
