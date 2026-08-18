"""Native-only diagnostic for DR2d final-token preservation and serializer path."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_abi as abi
from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_terminal_probe_graph as probe
from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import (
    PRE_SILICON_CORPUS,
)
from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_terminal_probe import (
    terminal_probe_expected,
    terminal_probe_expected_record,
)


def _run_native_diagnostic() -> int:
    case = PRE_SILICON_CORPUS[0]
    assert case.request_id == probe.DIAGNOSTIC_CASE1_REQUEST_ID
    print("=" * 72)
    print("PQC DR2d terminal probe - DIAGNOSTIC ONLY, NOT KeyGen validation")
    try:
        probe.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - native-only diagnostic fails closed
        print(
            "Backend: dr2d-mlkem512-kpke-keygen:terminal-probe:unavailable "
            f"({type(exc).__name__}: {exc})"
        )
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used.")
        return 2
    print(f"Backend: {probe.BACKEND_LABEL}")
    try:
        actual = probe.run_case1_terminal_probe_record(case.d, case.request_id)
    except Exception as exc:  # noqa: BLE001 - diagnostic failure is explicit
        print(f"CASE1 ERROR ({type(exc).__name__}: {exc})")
        return 1
    expected_record = terminal_probe_expected_record(case.request_id)
    if actual != expected_record:
        print("CASE1 FAIL: complete final-token/serializer terminal record mismatch")
        return 1
    if terminal_probe_expected(case.request_id) != abi.parse_result(
        actual, case.request_id
    ):
        print("CASE1 FAIL: terminal record payload parse mismatch")
        return 1
    print("CASE1 PASS: known canonical final token reached exact 1,588-byte record")
    print("NOT A DR2d KeyGen pass; production 25/25 remains required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_native_diagnostic())
