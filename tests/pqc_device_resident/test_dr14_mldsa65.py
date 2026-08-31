# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and NIST ACVP reference validation for DR14 (ML-DSA-65 KeyGen, Sign, Verify)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class DR14KeyGenCase:
    tc_id: int
    test_name: str
    seed: bytes
    expected_pk: bytes
    expected_sk: bytes
    request_id: int


@dataclass(frozen=True)
class DR14SignCase:
    tc_id: int
    test_name: str
    sk: bytes
    m_or_mu: bytes
    external_mu: bool
    expected_sig: bytes
    request_id: int


@dataclass(frozen=True)
class DR14VerifyCase:
    tc_id: int
    test_name: str
    pk: bytes
    sig: bytes
    m_or_mu: bytes
    external_mu: bool
    expected_valid: bool
    reason: str
    request_id: int


def _load_keygen_corpus() -> tuple[DR14KeyGenCase, ...]:
    f = DATA_DIR / "dr14_nist_acvp_mldsa65_keygen_25.json"
    vectors = json.loads(f.read_text(encoding="utf-8"))
    return tuple(
        DR14KeyGenCase(
            tc_id=v["tcId"],
            test_name=f"acvp_mldsa65_keygen_tc{v['tcId']:03d}",
            seed=bytes.fromhex(v["seed"]),
            expected_pk=bytes.fromhex(v["expected_pk"]),
            expected_sk=bytes.fromhex(v["expected_sk"]),
            request_id=0xD1410000 + idx + 1,
        )
        for idx, v in enumerate(vectors)
    )


def _load_sign_corpus() -> tuple[DR14SignCase, ...]:
    f = DATA_DIR / "dr14_nist_acvp_mldsa65_sign_30.json"
    vectors = json.loads(f.read_text(encoding="utf-8"))
    return tuple(
        DR14SignCase(
            tc_id=v["tcId"],
            test_name=f"acvp_mldsa65_sign_tc{v['tcId']:03d}",
            sk=bytes.fromhex(v["sk"]),
            m_or_mu=bytes.fromhex(v["m_or_mu"]),
            external_mu=v["externalMu"],
            expected_sig=bytes.fromhex(v["expected_signature"]),
            request_id=0xD1420000 + idx + 1,
        )
        for idx, v in enumerate(vectors)
    )


def _load_verify_corpus() -> tuple[DR14VerifyCase, ...]:
    f = DATA_DIR / "dr14_nist_acvp_mldsa65_verify_30.json"
    vectors = json.loads(f.read_text(encoding="utf-8"))
    return tuple(
        DR14VerifyCase(
            tc_id=v["tcId"],
            test_name=f"acvp_mldsa65_verify_tc{v['tcId']:03d}",
            pk=bytes.fromhex(v["pk"]),
            sig=bytes.fromhex(v["signature"]),
            m_or_mu=bytes.fromhex(v["m_or_mu"]),
            external_mu=v["externalMu"],
            expected_valid=v["expected_valid"],
            reason=v.get("reason", ""),
            request_id=0xD1430000 + idx + 1,
        )
        for idx, v in enumerate(vectors)
    )


KEYGEN_CORPUS = _load_keygen_corpus()
SIGN_CORPUS = _load_sign_corpus()
VERIFY_CORPUS = _load_verify_corpus()

assert len(KEYGEN_CORPUS) == 25
assert len(SIGN_CORPUS) == 30
assert len(VERIFY_CORPUS) == 30

KEYGEN_EXPECTED = {case.test_name: (case.expected_pk, case.expected_sk) for case in KEYGEN_CORPUS}
SIGN_EXPECTED = {case.test_name: case.expected_sig for case in SIGN_CORPUS}
VERIFY_EXPECTED = {case.test_name: case.expected_valid for case in VERIFY_CORPUS}

TOTAL_DR14_CASES = len(KEYGEN_CORPUS) + len(SIGN_CORPUS) + len(VERIFY_CORPUS)
assert TOTAL_DR14_CASES == 85


class DR14ReferenceTests(unittest.TestCase):
    def test_dr14_case_counts(self) -> None:
        self.assertEqual(len(KEYGEN_CORPUS), 25)
        self.assertEqual(len(SIGN_CORPUS), 30)
        self.assertEqual(len(VERIFY_CORPUS), 30)
        self.assertEqual(TOTAL_DR14_CASES, 85)

    def test_dr14_vector_structures(self) -> None:
        for case in KEYGEN_CORPUS:
            with self.subTest(kg_case=case.test_name):
                self.assertEqual(len(case.seed), 32)
                self.assertEqual(len(case.expected_pk), 1952)
                self.assertEqual(len(case.expected_sk), 4032)

        for case in SIGN_CORPUS:
            with self.subTest(sign_case=case.test_name):
                self.assertEqual(len(case.sk), 4032)
                self.assertEqual(len(case.expected_sig), 3309)

        for case in VERIFY_CORPUS:
            with self.subTest(ver_case=case.test_name):
                self.assertEqual(len(case.pk), 1952)
                self.assertEqual(len(case.sig), 3309)
                self.assertIsInstance(case.expected_valid, bool)


if __name__ == "__main__":
    unittest.main()
