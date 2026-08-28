# SPDX-License-Identifier: Apache-2.0
"""Host unit tests for DR7 (ML-KEM-512 ML-KEM.Decaps)."""
import json
import zlib
from pathlib import Path
import pytest

from phoenix_sdr_dsp.pqc import dr7_mlkem512_decaps_abi as abi
from tests.pqc_device_resident.dr7_reference import mlkem512_decaps_reference

VECTORS_PATH = Path(__file__).parent / "data" / "dr7_nist_acvp_mlkem512_decaps_25.json"


def test_dr7_abi_contract():
    desc, req = abi.validate_request(b"\x00" * 1632, b"\x01" * 768, request_id=42)
    assert len(desc) == 16
    assert len(req) == 2400
    assert desc[0] == 1
    assert desc[1] == 0x71
    assert desc[2] == 0x52

    # Fake result unpacking
    k = b"\x42" * 32
    crc = zlib.crc32(k)
    import struct
    header = struct.pack("<IIIII", abi.RESULT_MAGIC, 42, abi.STATUS_OK, 32, crc)
    unpacked = abi.unpack_result(header + k, expected_request_id=42)
    assert unpacked == k


def test_dr7_reference_acvp_all_25():
    with open(VECTORS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for case in data["cases"]:
        dk = bytes.fromhex(case["dk"])
        c = bytes.fromhex(case["c"])
        exp_k = bytes.fromhex(case["k"])

        act_k = mlkem512_decaps_reference(dk, c)
        assert act_k == exp_k, f"Mismatch on {case['tc_id']}"
