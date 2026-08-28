# SPDX-License-Identifier: Apache-2.0
"""Fail-closed native physical silicon gate for Milestone DR4 (ML-KEM-512 K-PKE.Decrypt)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr4_mlkem512_kpke_decrypt_graph as graph

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr4_nist_acvp_mlkem512_kpke_decrypt_25.json"

def main() -> int:
    print("=" * 72)
    print("PQC DR4 - complete ML-KEM-512 K-PKE.Decrypt closure")
    print(f"Backend: {graph.BACKEND_LABEL}")

    try:
        graph.require_hardware_runtime()
    except Exception as exc:
        print(f"HARDWARE INITIALIZATION ERROR: {exc}", file=sys.stderr)
        return 1

    doc = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = doc["cases"]

    passed = 0
    total = len(cases)

    for case in cases:
        tc_id = case["tcId"]
        dk_pke = bytes.fromhex(case["dkPke"])
        c = bytes.fromhex(case["c"])
        expected_m = bytes.fromhex(case["m"])

        try:
            actual_m = graph.run_hardware_kpke_decrypt(
                dk_pke=dk_pke,
                c=c,
                request_id=tc_id,
            )
        except Exception as exc:
            print(f"  acvp-tcId-{tc_id:02d}                     FAIL (device error: {exc})")
            continue

        if actual_m == expected_m:
            print(f"  acvp-tcId-{tc_id:02d}                     PASS")
            passed += 1
        else:
            print(f"  acvp-tcId-{tc_id:02d}                     FAIL (mismatch)")
            print(f"    Expected: {expected_m.hex()}")
            print(f"    Actual:   {actual_m.hex()}")

    print("-" * 72)
    print(f"TOTAL {passed}/{total} PASS")
    print("=" * 72)

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
