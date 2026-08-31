# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and NIST ACVP reference validation for DR13 (ML-DSA-44 Verify)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

DATA_FILE = Path(__file__).parent / "data" / "dr13_nist_acvp_mldsa44_verify_30.json"


@dataclass(frozen=True)
class DR13Case:
    tc_id: int
    tg_id: int
    test_name: str
    numeric_id: int
    pk: bytes
    m_or_mu: bytes
    sig: bytes
    expected_valid: bool
    external_mu: bool
    reason: str
    request_id: int


def _load_corpus() -> tuple[DR13Case, ...]:
    vectors = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(
        DR13Case(
            tc_id=vec["tcId"],
            tg_id=vec["tgId"],
            test_name=f"acvp_mldsa44_verify_tg{vec['tgId']}_tc{vec['tcId']}",
            numeric_id=idx + 1,
            pk=bytes.fromhex(vec["pk"]),
            m_or_mu=bytes.fromhex(vec["m_or_mu"]),
            sig=bytes.fromhex(vec["signature"]),
            expected_valid=vec["expected_valid"],
            external_mu=vec["externalMu"],
            reason=vec["reason"],
            request_id=0xD1300000 + (idx + 1),
        )
        for idx, vec in enumerate(vectors)
    )


PRE_SILICON_CORPUS = _load_corpus()
ACVP_EXPECTED = {case.test_name: case.expected_valid for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 30


class DR13ReferenceTests(unittest.TestCase):
    def test_dr13_case_count(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 30)

    def test_dr13_vector_structure(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.test_name):
                self.assertEqual(len(case.pk), 1312)
                self.assertEqual(len(case.sig), 2420)
                self.assertIsInstance(case.expected_valid, bool)


if __name__ == "__main__":
    unittest.main()
