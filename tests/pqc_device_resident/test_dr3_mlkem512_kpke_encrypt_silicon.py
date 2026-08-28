#!/usr/bin/env python3
"""Canonical physical silicon test runner for DR3: ML-KEM-512 K-PKE.Encrypt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr3_mlkem512_kpke_encrypt_abi as abi
from phoenix_sdr_dsp.pqc.dr3_mlkem512_kpke_encrypt_graph import (
    BACKEND_LABEL,
    require_hardware_runtime,
    run_hardware_kpke_encrypt,
)

CORPUS_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "dr3_nist_acvp_mlkem512_kpke_encrypt_25.json"
)


def main() -> int:
    require_hardware_runtime()

    corpus_doc = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = corpus_doc["cases"]

    print("=" * 72)
    print("PQC DR3 - complete ML-KEM-512 K-PKE.Encrypt closure")
    print(f"Backend: {BACKEND_LABEL}")

    passed = 0
    total = len(cases)

    for case in cases:
        tc_id = case["tcId"]
        name = f"acvp-tcId-{tc_id:02d}"
        ek = bytes.fromhex(case["ek"])
        m = bytes.fromhex(case["m"])
        r = bytes.fromhex(case["r"])
        expected_c = bytes.fromhex(case["c"])

        try:
            actual_c = run_hardware_kpke_encrypt(ek, m, r, request_id=tc_id)
            if actual_c == expected_c:
                print(f"  {name:<32} PASS")
                passed += 1
            else:
                print(f"  {name:<32} FAIL: ciphertext mismatch")
                print(f"    Expected: {expected_c[:32].hex()}...")
                print(f"    Actual:   {actual_c[:32].hex()}...")
                return 1
        except Exception as exc:
            print(f"  {name:<32} FAIL: {exc}")
            return 1

    print("-" * 72)
    print(f"TOTAL {passed}/{total} PASS")
    print("=" * 72)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
