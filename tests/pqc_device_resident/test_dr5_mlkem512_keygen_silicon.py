# SPDX-License-Identifier: Apache-2.0
"""Native-only Phoenix silicon gate for Milestone DR5 (ML-KEM-512 ML-KEM.KeyGen)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr5_mlkem512_keygen_graph as graph

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "dr5_nist_acvp_mlkem512_keygen_25.json"
EXPECTED_TOTAL = 25


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR5 - complete ML-KEM-512 ML-KEM.KeyGen closure")
    try:
        graph.require_hardware_runtime()
    except Exception as exc:
        print(f"Backend: dr5-mlkem512-keygen:unavailable ({type(exc).__name__}: {exc})")
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran.")
        return 2

    print(f"Backend: {graph.BACKEND_LABEL}")
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == EXPECTED_TOTAL

    passed = 0
    for case in cases:
        tc_id = case["tcId"]
        label = f"dr5_acvp_mlkem512_keygen_tc{tc_id:02d}"
        d = bytes.fromhex(case["d"])
        z = bytes.fromhex(case["z"])
        expected_ek = bytes.fromhex(case["ek"])
        expected_dk = bytes.fromhex(case["dk"])

        try:
            actual_ek, actual_dk = graph.run_mlkem512_keygen(d, z, request_id=tc_id)
        except Exception as exc:
            print(f"  {label:<36} ERROR ({type(exc).__name__}: {exc})")
            continue

        if actual_ek == expected_ek and actual_dk == expected_dk:
            passed += 1
            print(f"  {label:<36} PASS")
        else:
            ek_match = "OK" if actual_ek == expected_ek else "MISMATCH"
            dk_match = "OK" if actual_dk == expected_dk else "MISMATCH"
            print(f"  {label:<36} FAIL (ek={ek_match}, dk={dk_match})")

    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    print("-" * 72)
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")
    print("=" * 72)
    return 0 if passed == EXPECTED_TOTAL else 1


if __name__ == "__main__":
    raise SystemExit(_run_native_gate())
