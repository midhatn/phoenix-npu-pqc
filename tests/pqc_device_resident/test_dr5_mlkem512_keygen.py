# SPDX-License-Identifier: Apache-2.0
"""Host reference and contract validation test for Milestone DR5 (ML-KEM-512 ML-KEM.KeyGen)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from phoenix_sdr_dsp.pqc import dr5_mlkem512_keygen_abi as abi
from tests.pqc_device_resident.dr5_reference import mlkem512_keygen_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr5_nist_acvp_mlkem512_keygen_25.json"

@pytest.fixture
def acvp_corpus():
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return data["cases"]

def test_dr5_abi_contract():
    d_dummy = bytes(32)
    z_dummy = bytes(32)
    desc, req = abi.validate_request(d_dummy, z_dummy, request_id=51)
    assert len(desc) == abi.DESCRIPTOR_BYTES
    assert len(req) == abi.REQUEST_PAYLOAD_BYTES

def test_dr5_reference_acvp_all_25(acvp_corpus):
    passed = 0
    for case in acvp_corpus:
        tc_id = case["tcId"]
        d = bytes.fromhex(case["d"])
        z = bytes.fromhex(case["z"])
        expected_ek = bytes.fromhex(case["ek"])
        expected_dk = bytes.fromhex(case["dk"])

        actual_ek, actual_dk = mlkem512_keygen_reference(d, z)
        assert actual_ek == expected_ek, f"tcId {tc_id} failed ek match"
        assert actual_dk == expected_dk, f"tcId {tc_id} failed dk match"
        passed += 1

    print(f"\nDR5 Reference Oracle: {passed}/25 NIST ACVP cases passed 100% bit-exact!")

if __name__ == "__main__":
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    test_dr5_reference_acvp_all_25(data["cases"])
