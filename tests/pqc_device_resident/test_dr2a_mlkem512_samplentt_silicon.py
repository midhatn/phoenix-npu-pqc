"""Native-only Phoenix gate for the narrow DR2a SampleNTT graph."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2_mlkem512_samplentt_graph as graph
from tests.pqc_device_resident.dr2a_reference import samplentt_reference
from tests.pqc_device_resident.test_dr2_mlkem512_samplentt import PRE_SILICON_CORPUS

EXPECTED_TOTAL = len(PRE_SILICON_CORPUS)


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR2a - ML-KEM-512 bounded SHAKE128 SampleNTT")
    try:
        graph.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - physical gate must clearly fail closed
        print(f"Backend: dr2a-mlkem512-samplentt:unavailable ({type(exc).__name__}: {exc})")
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran.")
        return 2

    print(f"Backend: {graph.BACKEND_LABEL}")
    passed = 0
    for case in PRE_SILICON_CORPUS:
        expected = samplentt_reference(case.rho, case.j, case.i)
        try:
            actual = graph.run_mlkem512_samplentt(
                case.rho, case.j, case.i, case.request_id
            )
        except Exception as exc:  # noqa: BLE001 - a native failure remains a gate failure
            print(f"  {case.label:<32} ERROR ({type(exc).__name__}: {exc})")
            continue
        if not expected.limit_exceeded and actual == list(expected.coefficients):
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
