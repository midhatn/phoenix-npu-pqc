# SPDX-License-Identifier: Apache-2.0
"""DR12: 100% On-Device NIST FIPS 204 ML-DSA-44 Sign Physical Silicon Validation."""

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc.dr12_mldsa44_sign_graph import run_mldsa44_sign

DATA_PATH = Path(__file__).resolve().parent / "data" / "dr12_nist_acvp_mldsa44_sign_30.json"

def main() -> int:
    print("=" * 60)
    print("DR12: Complete NIST FIPS 204 ML-DSA-44 Sign Validation")
    print("Backend: dr12-mldsa44-sign:silicon (AMD Phoenix AIE2)")
    print("=" * 60)

    if not DATA_PATH.exists():
        print(f"FAIL: Missing test vector dataset at {DATA_PATH}")
        return 1

    vectors = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"Running {len(vectors)} NIST ACVP ML-DSA-44 Sign vectors on AMD Phoenix NPU...")

    passed = 0
    failures = []

    for idx, vec in enumerate(vectors, start=1):
        tc_id = vec["tcId"]
        tg_id = vec["tgId"]
        external_mu = vec["externalMu"]
        sk = bytes.fromhex(vec["sk"])
        m_or_mu = bytes.fromhex(vec["m_or_mu"])
        expected_sig = bytes.fromhex(vec["expected_signature"])
        rnd = bytes(32) # Deterministic signing per ACVP group

        test_name = f"acvp_mldsa44_sign_tg{tg_id}_tc{tc_id:02d}"

        try:
            silicon_sig = run_mldsa44_sign(
                sk=sk,
                m_or_mu=m_or_mu,
                rnd=rnd,
                external_mu=external_mu,
                request_id=idx,
            )

            if silicon_sig == expected_sig:
                print(f"  [{idx:02d}/{len(vectors)}] {test_name:<36}: PASS (100% bit-exact signature)")
                passed += 1
            else:
                print(f"  [{idx:02d}/{len(vectors)}] {test_name:<36}: FAIL (Signature mismatch)")
                print(f"    Expected : {expected_sig.hex()[:48]}...")
                print(f"    Silicon  : {silicon_sig.hex()[:48]}...")
                failures.append(test_name)
        except Exception as exc:
            print(f"  [{idx:02d}/{len(vectors)}] {test_name:<36}: FAIL (Exception: {exc})")
            failures.append(f"{test_name} ({exc})")

    print("-" * 60)
    print(f"TOTAL: {passed}/{len(vectors)} PASS ({'100% BIT-EXACT MATCH ON PHYSICAL SILICON' if passed == len(vectors) else 'FAILURES DETECTED'})")
    print("=" * 60)

    if passed != len(vectors):
        raise RuntimeError(f"DR12 Silicon validation failed ({len(failures)} failures)")
    return 0

def test_dr12_mldsa44_sign_silicon():
    assert main() == 0

if __name__ == "__main__":
    sys.exit(main())
