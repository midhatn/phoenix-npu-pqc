"""Native-only Phoenix gate for DR2b ML-KEM-512 eta1 noise-to-NTT."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2b_mlkem512_noise_ntt_graph as graph
from tests.pqc_device_resident.dr2b_reference import noise_ntt_reference
from tests.pqc_device_resident.test_dr2b_mlkem512_noise_ntt import PRE_SILICON_CORPUS

EXPECTED_TOTAL = len(PRE_SILICON_CORPUS)


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR2b - ML-KEM-512 SHAKE256 CBD3 NTT")
    try:
        graph.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - native gate must clearly fail closed
        print(
            "Backend: dr2b-mlkem512-noise-ntt:unavailable "
            f"({type(exc).__name__}: {exc})"
        )
        print(
            "UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran."
        )
        return 2

    print(f"Backend: {graph.BACKEND_LABEL}")
    passed = 0
    for case in PRE_SILICON_CORPUS:
        try:
            actual = graph.run_mlkem512_eta1_noise_ntt(
                case.sigma, case.counter, case.request_id
            )
        except Exception as exc:  # noqa: BLE001 - a native failure is a gate failure
            print(f"  {case.label:<32} ERROR ({type(exc).__name__}: {exc})")
            continue
        if actual == list(noise_ntt_reference(case.sigma, case.counter)):
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
