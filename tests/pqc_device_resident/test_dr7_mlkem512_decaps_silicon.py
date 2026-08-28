# SPDX-License-Identifier: Apache-2.0
"""Fail-closed silicon validation gate for Milestone DR7 (ML-KEM-512 ML-KEM.Decaps)."""
import json
import sys
import time
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr7_mlkem512_decaps_graph as graph

VECTORS_PATH = Path(__file__).parent / "data" / "dr7_nist_acvp_mlkem512_decaps_25.json"


def run_gate() -> int:
    print("=" * 72)
    print("PQC DR7 - complete ML-KEM-512 ML-KEM.Decaps closure")
    print(f"Backend: {graph.BACKEND_LABEL}")

    with open(VECTORS_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    passed = 0
    total = len(corpus["cases"])

    for case in corpus["cases"]:
        tc_id = case["tc_id"]
        dk = bytes.fromhex(case["dk"])
        c = bytes.fromhex(case["c"])
        exp_k = bytes.fromhex(case["k"])

        try:
            act_k = graph.run_mlkem512_decaps(dk, c, request_id=1)
            if act_k == exp_k:
                print(f"  {tc_id:<36} PASS")
                passed += 1
            else:
                print(f"  {tc_id:<36} FAIL (mismatch)")
                print(f"    Expected K: {exp_k.hex()}")
                print(f"    Actual   K: {act_k.hex()}")
        except Exception as exc:
            print(f"  {tc_id:<36} ERROR ({exc})")

    print("-" * 72)
    state = "PASS" if passed == total else "FAIL"
    print(f"TOTAL {passed}/{total} {state}")
    print("=" * 72)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_gate())
