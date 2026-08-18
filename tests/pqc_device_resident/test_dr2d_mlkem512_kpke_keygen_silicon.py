"""Native-only Phoenix gate for complete device-resident ML-KEM-512 K-PKE.KeyGen."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph as graph
from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import (
    ACVP_EXPECTED,
    PRE_SILICON_CORPUS,
)

EXPECTED_TOTAL = 25
assert len(PRE_SILICON_CORPUS) == EXPECTED_TOTAL


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR2d - complete ML-KEM-512 K-PKE.KeyGen closure")
    try:
        graph.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - native-only gates fail closed
        print(
            f"Backend: dr2d-mlkem512-kpke-keygen:unavailable ({type(exc).__name__}: {exc})"
        )
        print(
            "UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran."
        )
        return 2
    print(f"Backend: {graph.BACKEND_LABEL}")
    passed = 0
    for case in PRE_SILICON_CORPUS:
        try:
            actual = graph.run_mlkem512_kpke_keygen(case.d, case.request_id)
        except Exception as exc:  # noqa: BLE001 - native error is a gate failure
            print(f"  {case.label:<32} ERROR ({type(exc).__name__}: {exc})")
            continue
        tc_id = int(case.label[-2:])
        if actual == ACVP_EXPECTED[tc_id]:
            passed += 1
            print(f"  {case.label:<32} PASS")
        else:
            print(f"  {case.label:<32} FAIL")
    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    print("-" * 72)
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")
    print("=" * 72)
    return 0 if passed == EXPECTED_TOTAL else 1


if __name__ == "__main__":
    raise SystemExit(_run_native_gate())
