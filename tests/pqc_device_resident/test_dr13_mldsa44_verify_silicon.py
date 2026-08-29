# SPDX-License-Identifier: Apache-2.0
"""DR13: Complete NIST FIPS 204 ML-DSA-44 Signature Verification on AMD Phoenix NPU.

Validates 100% On-Device ML-DSA-44 Verify against official NIST ACVP test vectors
including both valid signatures and invalid mutated/norm-violating signatures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc.dr13_mldsa44_verify_graph import run_mldsa44_verify

VECTOR_FILE = REPO_ROOT / "tests" / "pqc_device_resident" / "data" / "dr13_nist_acvp_mldsa44_verify_30.json"

def main() -> int:
    print("=" * 60)
    print("DR13: Complete NIST FIPS 204 ML-DSA-44 Verify Validation")
    print("Backend: dr13-mldsa44-verify:silicon (AMD Phoenix AIE2)")
    print("=" * 60)

    if not VECTOR_FILE.exists():
        print(f"ERROR: Vector file not found: {VECTOR_FILE}")
        return 1

    vectors = json.loads(VECTOR_FILE.read_text(encoding="utf-8"))
    print(f"Running {len(vectors)} NIST ACVP ML-DSA-44 Verify vectors on AMD Phoenix NPU...")

    passed = 0
    failures = []

    for i, vec in enumerate(vectors, 1):
        tc_id = f"acvp_mldsa44_verify_tg{vec['tgId']}_tc{vec['tcId']}"
        pk = bytes.fromhex(vec["pk"])
        m_or_mu = bytes.fromhex(vec["m_or_mu"])
        sig = bytes.fromhex(vec["signature"])
        expected_valid = vec["expected_valid"]
        external_mu = vec["externalMu"]

        try:
            actual_valid = run_mldsa44_verify(
                pk=pk,
                m_or_mu=m_or_mu,
                sig=sig,
                external_mu=external_mu,
                request_id=i,
            )

            if actual_valid == expected_valid:
                passed += 1
                verdict_str = "VALID (Accepted)" if actual_valid else "INVALID (Rejected)"
                print(f"  [{i:02d}/{len(vectors):02d}] {tc_id:<40}: PASS ({verdict_str})")
            else:
                failures.append(tc_id)
                print(f"  [{i:02d}/{len(vectors):02d}] {tc_id:<40}: FAIL (Verdict mismatch)")
                print(f"    Expected : {expected_valid}")
                print(f"    Silicon  : {actual_valid}")
                print(f"    Reason   : {vec['reason']}")
        except Exception as exc:
            failures.append(tc_id)
            print(f"  [{i:02d}/{len(vectors):02d}] {tc_id:<40}: FAIL (Exception: {exc})")

    print("-" * 60)
    print(f"TOTAL: {passed}/{len(vectors)} PASS ({'100% BIT-EXACT MATCH ON PHYSICAL SILICON' if passed == len(vectors) else 'FAILURES DETECTED'})")
    print("=" * 60)

    if passed != len(vectors):
        raise RuntimeError(f"DR13 Silicon validation failed ({len(failures)} failures)")
    return 0

def test_dr13_mldsa44_verify_silicon():
    assert main() == 0

if __name__ == "__main__":
    sys.exit(main())
