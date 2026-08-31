# SPDX-License-Identifier: Apache-2.0
"""Host unit tests and NIST FIPS 202 reference validation for DR9."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import unittest

from phoenix_sdr_dsp.pqc import dr9_fips202_unified_abi as abi
from tests.pqc_device_resident.dr9_reference import compute_fips202_reference

DATA_FILE = Path(__file__).parent / "data" / "dr9_nist_fips202_vectors.json"


@dataclass(frozen=True)
class DR9Case:
    tc_id: str
    numeric_id: int
    func_name: str
    func_id: int
    msg: bytes
    out_len: int
    expected_digest: bytes
    request_id: int


def _load_corpus() -> tuple[DR9Case, ...]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(
        DR9Case(
            tc_id=c["tcId"],
            numeric_id=idx + 1,
            func_name=c["function"],
            func_id=c["func_id"],
            msg=bytes.fromhex(c["msg"]),
            out_len=c["out_len"],
            expected_digest=bytes.fromhex(c["expected_digest"]),
            request_id=0xD9000000 + (idx + 1),
        )
        for idx, c in enumerate(data["cases"])
    )


PRE_SILICON_CORPUS = _load_corpus()
ACVP_EXPECTED = {case.tc_id: case.expected_digest for case in PRE_SILICON_CORPUS}
assert len(PRE_SILICON_CORPUS) == 122


class DR9ReferenceTests(unittest.TestCase):
    def test_dr9_abi_contract(self) -> None:
        msg = b"Hello, AIE2 FIPS 202 service!"
        desc = abi.pack_dr9_descriptor("SHA3-256", len(msg), 32, request_id=42)
        req = abi.pack_dr9_request(msg)
        self.assertEqual(len(desc), abi.DESCRIPTOR_BYTES)
        self.assertEqual(len(req), abi.REQ_BYTES)
        header = abi.pack_dr9_result_header(42, 0, 32, 0x12345678)
        self.assertEqual(len(header), abi.RESULT_HEADER_BYTES)

    def test_dr9_reference_all_122(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 122)
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.tc_id):
                digest = compute_fips202_reference(case.func_name, case.msg, case.out_len)
                self.assertEqual(digest, case.expected_digest)


if __name__ == "__main__":
    unittest.main()
