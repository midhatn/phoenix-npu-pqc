# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and NIST ACVP reference validation for DR8 (ML-KEM 512, 768, 1024)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

from tests.pqc_device_resident.dr8_reference import (
    PARAMS_512,
    PARAMS_768,
    PARAMS_1024,
    mlkem_decaps as ref_decaps,
    mlkem_encaps as ref_encaps,
    mlkem_keygen as ref_keygen,
)

DATA_DIR = Path(__file__).parent / "data"
PATH_512 = DATA_DIR / "dr7_nist_acvp_mlkem512_decaps_25.json"
PATH_768 = DATA_DIR / "dr8_nist_acvp_mlkem768_25.json"
PATH_1024 = DATA_DIR / "dr8_nist_acvp_mlkem1024_25.json"


@dataclass(frozen=True)
class DR8Case:
    param_set: str
    tc_id: str
    numeric_id: int
    is_full_cycle: bool
    d: bytes | None
    z: bytes | None
    m: bytes | None
    ek: bytes | None
    dk: bytes
    c: bytes
    expected_k: bytes
    expected_ek: bytes | None
    expected_c: bytes | None
    request_id: int


def _load_corpus() -> tuple[DR8Case, ...]:
    cases: list[DR8Case] = []
    
    # 1. ML-KEM-512 (25 cases)
    data_512 = json.loads(PATH_512.read_text(encoding="utf-8"))
    for idx, c in enumerate(data_512["cases"]):
        tc = c.get("tcId") or c.get("tc_id", f"512_case_{idx+1}")
        dk = bytes.fromhex(c["dk"])
        c_bytes = bytes.fromhex(c["c"])
        k = bytes.fromhex(c["k"])
        cases.append(
            DR8Case(
                param_set="ML-KEM-512",
                tc_id=tc,
                numeric_id=len(cases) + 1,
                is_full_cycle=False,
                d=None,
                z=None,
                m=None,
                ek=None,
                dk=dk,
                c=c_bytes,
                expected_k=k,
                expected_ek=None,
                expected_c=None,
                request_id=0xD8000000 + len(cases) + 1,
            )
        )

    # 2. ML-KEM-768 (25 cases)
    data_768 = json.loads(PATH_768.read_text(encoding="utf-8"))
    for idx, c in enumerate(data_768["cases"]):
        tc = c.get("tcId") or c.get("tc_id", f"768_case_{idx+1}")
        is_paired = "dr8_paired" in tc or c.get("is_rejection", False)
        is_full = not is_paired and "d" in c and "m" in c
        if is_full:
            d = bytes.fromhex(c["d"])
            z = bytes.fromhex(c["z"])
            m = bytes.fromhex(c["m"])
            ek = bytes.fromhex(c["ek"])
            dk = bytes.fromhex(c["dk"])
            c_bytes = bytes.fromhex(c["c"])
            k = bytes.fromhex(c["k"])
            cases.append(
                DR8Case(
                    param_set="ML-KEM-768",
                    tc_id=tc,
                    numeric_id=len(cases) + 1,
                    is_full_cycle=True,
                    d=d,
                    z=z,
                    m=m,
                    ek=ek,
                    dk=dk,
                    c=c_bytes,
                    expected_k=k,
                    expected_ek=ek,
                    expected_c=c_bytes,
                    request_id=0xD8000000 + len(cases) + 1,
                )
            )
        else:
            dk = bytes.fromhex(c["dk"])
            c_bytes = bytes.fromhex(c["c"])
            k = bytes.fromhex(c["k"])
            cases.append(
                DR8Case(
                    param_set="ML-KEM-768",
                    tc_id=tc,
                    numeric_id=len(cases) + 1,
                    is_full_cycle=False,
                    d=None,
                    z=None,
                    m=None,
                    ek=None,
                    dk=dk,
                    c=c_bytes,
                    expected_k=k,
                    expected_ek=None,
                    expected_c=None,
                    request_id=0xD8000000 + len(cases) + 1,
                )
            )

    # 3. ML-KEM-1024 (25 cases)
    data_1024 = json.loads(PATH_1024.read_text(encoding="utf-8"))
    for idx, c in enumerate(data_1024["cases"]):
        tc = c.get("tcId") or c.get("tc_id", f"1024_case_{idx+1}")
        is_paired = "dr8_paired" in tc or c.get("is_rejection", False)
        is_full = not is_paired and "d" in c and "m" in c
        if is_full:
            d = bytes.fromhex(c["d"])
            z = bytes.fromhex(c["z"])
            m = bytes.fromhex(c["m"])
            ek = bytes.fromhex(c["ek"])
            dk = bytes.fromhex(c["dk"])
            c_bytes = bytes.fromhex(c["c"])
            k = bytes.fromhex(c["k"])
            cases.append(
                DR8Case(
                    param_set="ML-KEM-1024",
                    tc_id=tc,
                    numeric_id=len(cases) + 1,
                    is_full_cycle=True,
                    d=d,
                    z=z,
                    m=m,
                    ek=ek,
                    dk=dk,
                    c=c_bytes,
                    expected_k=k,
                    expected_ek=ek,
                    expected_c=c_bytes,
                    request_id=0xD8000000 + len(cases) + 1,
                )
            )
        else:
            dk = bytes.fromhex(c["dk"])
            c_bytes = bytes.fromhex(c["c"])
            k = bytes.fromhex(c["k"])
            cases.append(
                DR8Case(
                    param_set="ML-KEM-1024",
                    tc_id=tc,
                    numeric_id=len(cases) + 1,
                    is_full_cycle=False,
                    d=None,
                    z=None,
                    m=None,
                    ek=None,
                    dk=dk,
                    c=c_bytes,
                    expected_k=k,
                    expected_ek=None,
                    expected_c=None,
                    request_id=0xD8000000 + len(cases) + 1,
                )
            )

    return tuple(cases)


PRE_SILICON_CORPUS = _load_corpus()
ACVP_EXPECTED = {case.tc_id: case.expected_k for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 75


class DR8ReferenceTests(unittest.TestCase):
    def test_dr8_case_count(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 75)

    def test_dr8_reference_all_75(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=f"{case.param_set}_{case.tc_id}"):
                if case.param_set == "ML-KEM-512":
                    params = PARAMS_512
                elif case.param_set == "ML-KEM-768":
                    params = PARAMS_768
                else:
                    params = PARAMS_1024

                if case.is_full_cycle:
                    assert case.d is not None and case.z is not None and case.m is not None
                    ek, dk = ref_keygen(case.d, case.z, params)
                    self.assertEqual(ek, case.expected_ek)
                    self.assertEqual(dk, case.dk)
                    c, k = ref_encaps(ek, case.m, params)
                    self.assertEqual(c, case.expected_c)
                    self.assertEqual(k, case.expected_k)
                    k_dec = ref_decaps(dk, c, params)
                    self.assertEqual(k_dec, case.expected_k)
                else:
                    k_dec = ref_decaps(case.dk, case.c, params)
                    self.assertEqual(k_dec, case.expected_k)


if __name__ == "__main__":
    unittest.main()
