# SPDX-License-Identifier: Apache-2.0
"""Host reference and contract validation test for Milestone DR6 (ML-KEM-512 ML-KEM.Encaps)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from phoenix_sdr_dsp.pqc import dr6_mlkem512_encaps_abi as abi
from tests.pqc_device_resident.dr6_reference import mlkem512_encaps_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr6_nist_acvp_mlkem512_encaps_25.json"


@pytest.fixture
def acvp_corpus():
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return data["cases"]


def test_dr6_abi_contract():
    ek_dummy = bytes(800)
    m_dummy = bytes(32)
    desc, req = abi.validate_request(ek_dummy, m_dummy, request_id=61)
    assert len(desc) == abi.DESCRIPTOR_BYTES
    assert len(req) == abi.REQUEST_PAYLOAD_BYTES


def test_dr6_reference_acvp_all_25(acvp_corpus):
    passed = 0
    for case in acvp_corpus:
        tc_id = case["tcId"]
        ek = bytes.fromhex(case["ek"])
        m = bytes.fromhex(case["m"])
        expected_c = bytes.fromhex(case["c"])
        expected_k = bytes.fromhex(case["k"])

        actual_c, actual_k = mlkem512_encaps_reference(ek, m)
        assert actual_c == expected_c, f"tcId {tc_id} failed c match"
        assert actual_k == expected_k, f"tcId {tc_id} failed k match"
        passed += 1

    print(f"\nDR6 Reference Oracle: {passed}/25 NIST ACVP cases passed 100% bit-exact!")


if __name__ == "__main__":
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    test_dr6_reference_acvp_all_25(data["cases"])
