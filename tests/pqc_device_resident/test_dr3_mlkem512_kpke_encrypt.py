"""Host-preflight contract and reference suite for DR3 ML-KEM-512 K-PKE.Encrypt."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

from phoenix_sdr_dsp.pqc import dr3_mlkem512_kpke_encrypt_abi as abi
from tests.pqc_device_resident.dr3_reference import kpke_encrypt_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr3_nist_acvp_mlkem512_kpke_encrypt_25.json"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    tc_id: int
    ek: bytes
    m: bytes
    r: bytes
    expected_c: bytes
    request_id: int


_DATA = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
PRE_SILICON_CORPUS = tuple(
    CorpusCase(
        label=f"acvp-tcId-{case['tcId']:02d}",
        tc_id=case["tcId"],
        ek=bytes.fromhex(case["ek"]),
        m=bytes.fromhex(case["m"]),
        r=bytes.fromhex(case["r"]),
        expected_c=bytes.fromhex(case["c"]),
        request_id=0xD3000000 + case["tcId"],
    )
    for case in _DATA["cases"]
)
ACVP_EXPECTED = {case.tc_id: case.expected_c for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 25


class DR3ReferenceTests(unittest.TestCase):
    def test_dr3_descriptor_structure(self) -> None:
        desc = abi.build_descriptor(0x12345678)
        self.assertEqual(len(desc), 16)
        self.assertEqual(desc[0], 1)
        self.assertEqual(desc[1], 0x31)
        self.assertEqual(desc[2], 0x52)
        self.assertEqual(desc[4], 2)  # k
        self.assertEqual(desc[5], 3)  # eta1
        self.assertEqual(desc[6], 2)  # eta2

    def test_dr3_request_packing_and_validation(self) -> None:
        ek = b"\xaa" * 800
        m = b"\xbb" * 32
        r = b"\xcc" * 32
        desc, req = abi.validate_request(ek, m, r, request_id=42)
        self.assertEqual(len(desc), 16)
        self.assertEqual(len(req), 864)
        self.assertEqual(req[:800], ek)
        self.assertEqual(req[800:832], m)
        self.assertEqual(req[832:864], r)

    def test_dr3_reference_matches_acvp(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 25)
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                actual_c = kpke_encrypt_reference(case.ek, case.m, case.r)
                self.assertEqual(actual_c, case.expected_c)


if __name__ == "__main__":
    unittest.main()
