# SPDX-License-Identifier: Apache-2.0
"""DR11: ML-DSA-44 KeyGen Physical Silicon Validation Suite."""

import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr11_mldsa44_keygen_graph import run_mldsa44_keygen

DATA_FILE = Path(__file__).resolve().parent / "data" / "dr11_nist_acvp_mldsa44_25.json"

def main():
    print("===========================================================")
    print("DR11: Complete NIST FIPS 204 ML-DSA-44 KeyGen Validation")
    print("Backend: dr11-mldsa44-keygen:silicon (AMD Phoenix AIE2)")
    print("===========================================================")

    if not DATA_FILE.exists():
        print(f"Error: test vectors file {DATA_FILE} not found")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    total = len(cases)
    passed = 0

    print(f"Running {total} NIST ACVP ML-DSA-44 KeyGen vectors on AMD Phoenix NPU...")

    for i, tc in enumerate(cases, 1):
        tc_id = tc["tcId"]
        seed = bytes.fromhex(tc["seed"])
        exp_pk = tc["expected_pk"].lower()
        exp_sk = tc["expected_sk"].lower()

        try:
            pk, sk = run_mldsa44_keygen(seed, request_id=i)
            actual_pk = pk.hex().lower()
            actual_sk = sk.hex().lower()

            if actual_pk == exp_pk and actual_sk == exp_sk:
                passed += 1
                print(f"  [{i:02d}/{total:02d}] {tc_id:<35}: PASS (100% bit-exact pk & sk)")
            else:
                print(f"  [{i:02d}/{total:02d}] {tc_id:<35}: FAIL (Mismatch)")
                if actual_pk != exp_pk:
                    print(f"    PK Mismatch!")
                    print(f"      Exp: {exp_pk[:40]}...")
                    print(f"      Act: {actual_pk[:40]}...")
                if actual_sk != exp_sk:
                    print(f"    SK Mismatch!")
                    print(f"      Exp: {exp_sk[:40]}...")
                    print(f"      Act: {actual_sk[:40]}...")
                sys.exit(1)
        except Exception as exc:
            print(f"  [{i:02d}/{total:02d}] {tc_id:<35}: FAIL (Exception: {exc})")
            sys.exit(1)

    print("-----------------------------------------------------------")
    print(f"TOTAL: {passed}/{total} PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)")
    print("===========================================================")

if __name__ == "__main__":
    main()
