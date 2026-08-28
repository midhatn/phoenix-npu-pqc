"""Host-preflight contract and reference suite for DR3 ML-KEM-512 K-PKE.Encrypt."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from phoenix_sdr_dsp.pqc import dr3_mlkem512_kpke_encrypt_abi as abi
from tests.pqc_device_resident.dr3_reference import kpke_encrypt_reference

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr3_nist_acvp_mlkem512_kpke_encrypt_25.json"


@pytest.fixture(scope="module")
def acvp_corpus() -> list[dict]:
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return data["cases"]


def test_dr3_descriptor_structure() -> None:
    desc = abi.build_descriptor(0x12345678)
    assert len(desc) == 16
    assert desc[0] == 1
    assert desc[1] == 0x31
    assert desc[2] == 0x52
    assert desc[4] == 2  # k
    assert desc[5] == 3  # eta1
    assert desc[6] == 2  # eta2


def test_dr3_request_packing_and_validation() -> None:
    ek = b"\xaa" * 800
    m = b"\xbb" * 32
    r = b"\xcc" * 32
    desc, req = abi.validate_request(ek, m, r, request_id=42)
    assert len(desc) == 16
    assert len(req) == 864
    assert req[:800] == ek
    assert req[800:832] == m
    assert req[832:864] == r


def test_dr3_reference_matches_acvp(acvp_corpus: list[dict]) -> None:
    assert len(acvp_corpus) == 25
    for case in acvp_corpus:
        tc_id = case["tcId"]
        ek = bytes.fromhex(case["ek"])
        m = bytes.fromhex(case["m"])
        r = bytes.fromhex(case["r"])
        expected_c = case["c"]

        actual_c = kpke_encrypt_reference(ek, m, r).hex()
        assert actual_c.upper() == expected_c.upper(), f"Mismatch on tcId {tc_id}"
