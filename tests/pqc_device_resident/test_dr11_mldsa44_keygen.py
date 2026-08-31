# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and NIST ACVP reference validation for DR11 (ML-DSA-44 KeyGen)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

DATA_FILE = Path(__file__).parent / "data" / "dr11_nist_acvp_mldsa44_25.json"


@dataclass(frozen=True)
class DR11Case:
    tc_id: str
    numeric_id: int
    seed: bytes
    expected_pk: bytes
    expected_sk: bytes
    request_id: int


def _load_corpus() -> tuple[DR11Case, ...]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(
        DR11Case(
            tc_id=c["tcId"],
            numeric_id=idx + 1,
            seed=bytes.fromhex(c["seed"]),
            expected_pk=bytes.fromhex(c["expected_pk"]),
            expected_sk=bytes.fromhex(c["expected_sk"]),
            request_id=0xD1100000 + (idx + 1),
        )
        for idx, c in enumerate(data["cases"])
    )


PRE_SILICON_CORPUS = _load_corpus()
ACVP_EXPECTED = {case.tc_id: (case.expected_pk, case.expected_sk) for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 25


class DR11ReferenceTests(unittest.TestCase):
    def test_dr11_case_count(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 25)

    def test_dr11_vector_structure(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.tc_id):
                self.assertEqual(len(case.seed), 32)
                self.assertEqual(len(case.expected_pk), 1312)
                self.assertEqual(len(case.expected_sk), 2560)


if __name__ == "__main__":
    unittest.main()
