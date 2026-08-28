# SPDX-License-Identifier: Apache-2.0
"""Host reference and contract validation test for Milestone DR4 (ML-KEM-512 K-PKE.Decrypt)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from phoenix_sdr_dsp.pqc import dr4_mlkem512_kpke_decrypt_abi as abi
from tests.pqc_device_resident.dr4_reference import kpke_decrypt_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr4_nist_acvp_mlkem512_kpke_decrypt_25.json"

@pytest.fixture
def acvp_corpus():
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return data["cases"]

def test_dr4_abi_contract():
    dk_dummy = bytes(768)
    c_dummy = bytes(768)
    desc, req = abi.validate_request(dk_dummy, c_dummy, request_id=42)
    assert len(desc) == abi.DESCRIPTOR_BYTES
    assert len(req) == abi.REQUEST_PAYLOAD_BYTES

def test_dr4_reference_acvp_all_25(acvp_corpus):
    passed = 0
    for case in acvp_corpus:
        tc_id = case["tcId"]
        dk_pke = bytes.fromhex(case["dkPke"])
        c = bytes.fromhex(case["c"])
        expected_m = bytes.fromhex(case["m"])

        actual_m = kpke_decrypt_reference(dk_pke, c)
        assert actual_m == expected_m, f"tcId {tc_id} failed decrypt"
        passed += 1

    print(f"\nDR4 Reference Oracle: {passed}/25 NIST ACVP cases passed 100% bit-exact!")

if __name__ == "__main__":
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    test_dr4_reference_acvp_all_25(data["cases"])
