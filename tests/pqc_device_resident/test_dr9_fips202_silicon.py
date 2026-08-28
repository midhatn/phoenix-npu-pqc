# SPDX-License-Identifier: Apache-2.0
"""DR9 Reusable NIST FIPS 202 NPU Service Silicon Validation Suite."""

import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr9_fips202_graph import run_fips202_service

DATA_FILE = Path(__file__).resolve().parent / "data" / "dr9_nist_fips202_vectors.json"

def main():
    print("===========================================================")
    print("DR9: Reusable NIST FIPS 202 NPU Service Silicon Validation")
    print("Backend: dr9-fips202:silicon (AMD Phoenix AIE2)")
    print("===========================================================")

    if not DATA_FILE.exists():
        print(f"Error: test vectors file {DATA_FILE} not found")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    total = len(cases)
    passed = 0

    print(f"Running {total} NIST FIPS 202 vectors across SHA3-224/256/384/512 and SHAKE128/256...")

    for i, tc in enumerate(cases, 1):
        tc_id = tc["tcId"]
        func = tc["function"]
        msg = bytes.fromhex(tc["msg"])
        out_len = tc["out_len"]
        expected = bytes.fromhex(tc["expected_digest"])

        try:
            actual = run_fips202_service(func, msg, out_len=out_len, request_id=i)
            if actual == expected:
                passed += 1
                if i <= 15 or i % 20 == 0 or i == total:
                    print(f"  [{i:03d}/{total:03d}] {tc_id:<45}: PASS")
            else:
                print(f"  [{i:03d}/{total:03d}] {tc_id:<45}: FAIL (Mismatch)")
                print(f"    Expected: {expected.hex()[:32]}...")
                print(f"    Actual:   {actual.hex()[:32]}...")
                sys.exit(1)
        except Exception as exc:
            print(f"  [{i:03d}/{total:03d}] {tc_id:<45}: FAIL (Exception: {exc})")
            sys.exit(1)

    print("-----------------------------------------------------------")
    print(f"TOTAL: {passed}/{total} PASS (100% BIT-EXACT MATCH ON PHYSICAL SILICON)")
    print("===========================================================")

if __name__ == "__main__":
    main()
