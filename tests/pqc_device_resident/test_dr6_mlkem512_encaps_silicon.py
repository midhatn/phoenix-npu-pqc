# SPDX-License-Identifier: Apache-2.0
"""Native-only Phoenix silicon gate for Milestone DR6 (ML-KEM-512 ML-KEM.Encaps)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr6_mlkem512_encaps_graph as graph

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr6_nist_acvp_mlkem512_encaps_25.json"
EXPECTED_TOTAL = 25


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR6 - complete ML-KEM-512 ML-KEM.Encaps closure")
    try:
        graph.require_hardware_runtime()
    except Exception as exc:
        print(f"Backend: dr6-mlkem512-encaps:unavailable ({type(exc).__name__}: {exc})")
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran.")
        return 2

    print(f"Backend: {graph.BACKEND_LABEL}")
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == EXPECTED_TOTAL

    passed = 0
    for case in cases:
        tc_id = case["tcId"]
        label = f"dr6_acvp_mlkem512_encaps_tc{tc_id:02d}"
        ek = bytes.fromhex(case["ek"])
        m = bytes.fromhex(case["m"])
        expected_c = bytes.fromhex(case["c"])
        expected_k = bytes.fromhex(case["k"])

        try:
            actual_c, actual_k = graph.run_mlkem512_encaps(ek, m, request_id=tc_id)
        except Exception as exc:
            print(f"  {label:<36} ERROR ({type(exc).__name__}: {exc})")
            continue

        if actual_c == expected_c and actual_k == expected_k:
            passed += 1
            print(f"  {label:<36} PASS")
        else:
            c_match = "OK" if actual_c == expected_c else "MISMATCH"
            k_match = "OK" if actual_k == expected_k else "MISMATCH"
            print(f"  {label:<36} FAIL (c={c_match}, k={k_match})")

    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    print("-" * 72)
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")
    print("=" * 72)
    return 0 if passed == EXPECTED_TOTAL else 1


if __name__ == "__main__":
    raise SystemExit(_run_native_gate())
