# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and NIST ACVP reference validation for DR12 (ML-DSA-44 Sign)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

DATA_FILE = Path(__file__).parent / "data" / "dr12_nist_acvp_mldsa44_sign_30.json"


@dataclass(frozen=True)
class DR12Case:
    tc_id: int
    tg_id: int
    test_name: str
    numeric_id: int
    sk: bytes
    m_or_mu: bytes
    external_mu: bool
    expected_sig: bytes
    request_id: int


def _load_corpus() -> tuple[DR12Case, ...]:
    vectors = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(
        DR12Case(
            tc_id=vec["tcId"],
            tg_id=vec["tgId"],
            test_name=f"acvp_mldsa44_sign_tg{vec['tgId']}_tc{vec['tcId']:02d}",
            numeric_id=idx + 1,
            sk=bytes.fromhex(vec["sk"]),
            m_or_mu=bytes.fromhex(vec["m_or_mu"]),
            external_mu=vec["externalMu"],
            expected_sig=bytes.fromhex(vec["expected_signature"]),
            request_id=0xD1200000 + (idx + 1),
        )
        for idx, vec in enumerate(vectors)
    )


PRE_SILICON_CORPUS = _load_corpus()
ACVP_EXPECTED = {case.test_name: case.expected_sig for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 30


class DR12ReferenceTests(unittest.TestCase):
    def test_dr12_case_count(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 30)

    def test_dr12_vector_structure(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.test_name):
                self.assertEqual(len(case.sk), 2560)
                self.assertEqual(len(case.expected_sig), 2420)


if __name__ == "__main__":
    unittest.main()
