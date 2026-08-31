"""Native-only Phoenix gate for the narrow DR1 ML-DSA-44 ExpandA/RejNTT graph.

This module is a physical gate only. It reuses the exact 33-case corpus and the
independent ``hashlib``-based oracle already reviewed in
``tests/pqc_device_resident/test_dr1_mldsa44_rejntt.py`` and dispatches every
case through the production DR1 graph on Phoenix silicon. There is no host
execution backend, no fallback backend, and no skip path. The host computes an
independent oracle only to verify the terminal result returned by the NPU. If
the native IRON/XRT/Phoenix runtime is unavailable the gate reports
``unavailable`` and exits non-zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from datetime import datetime, timezone
import json
import os
import time

from phoenix_sdr_dsp.pqc import dr1_mldsa44_rejntt_graph as graph
from tests.pqc_device_resident.dr1_reference import expanda_rejntt_reference
from tests.pqc_device_resident.test_dr1_mldsa44_rejntt import (
    DR1_CORPUS_SHA256,
    FINGERPRINT_BY_LABEL,
    PRE_SILICON_CORPUS,
    _coefficient_digest,
    pre_silicon_corpus_sha256,
)

EXPECTED_TOTAL = len(PRE_SILICON_CORPUS)
RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR1 - ML-DSA-44 ExpandA rejection-sampling NTT")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        graph.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - a native-only gate must fail closed
        print(
            "Backend: dr1-mldsa44-expanda-rejntt:unavailable "
            f"({type(exc).__name__}: {exc})"
        )
        print(
            "UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran."
        )
        return 2

    actual_corpus_sha256 = pre_silicon_corpus_sha256()
    if actual_corpus_sha256 != DR1_CORPUS_SHA256:
        print(
            "CORPUS ERROR: serialized DR1 corpus SHA-256 "
            f"{actual_corpus_sha256} != frozen {DR1_CORPUS_SHA256}"
        )
        return 1

    print(f"Backend: {graph.BACKEND_LABEL}")
    print(f"Corpus SHA-256: {DR1_CORPUS_SHA256}")

    device_info: dict[str, str] = {
        "device_name": "Phoenix AIE2",
        "device_id": "0",
        "driver": "amdnpu",
        "firmware": "aie2",
    }
    try:
        import pyxrt
        dev = pyxrt.device(0)
        dev_name = dev.get_info(pyxrt.xrt_info_device.name)
        if dev_name:
            device_info["device_name"] = str(dev_name)
        bdf = dev.get_info(pyxrt.xrt_info_device.bdf)
        if bdf:
            device_info["bdf"] = str(bdf)
    except Exception:
        pass

    try:
        artifact_info = graph.get_kernel_artifact_info(REPO_ROOT)
    except Exception as exc:
        print(f"ERROR: failed to get kernel artifact info: {exc}")
        return 1

    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr1_case_{idx:03d}_{case.label}"
        t_case_start = time.perf_counter_ns()
        expected = expanda_rejntt_reference(case.rho, case.j, case.i)
        try:
            actual = graph.run_mldsa44_expanda_rejntt(
                case.rho, case.j, case.i, case.request_id
            )
        except Exception as exc:  # noqa: BLE001 - a native error is a gate failure
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  {case.label:<28} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_case_duration = time.perf_counter_ns() - t_case_start
        completed += 1
        test_buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "rho_hex": case.rho.hex(),
            "j": case.j,
            "i": case.i,
            "request_id": case.request_id,
            "output_coefficients": actual,
            "fingerprint_sha256": _coefficient_digest(actual),
        })

        if (
            not expected.limit_exceeded
            and actual == list(expected.coefficients)
            and _coefficient_digest(actual) == FINGERPRINT_BY_LABEL[case.label]
        ):
            passed += 1
            print(f"  {case.label:<28} PASS")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  {case.label:<28} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "oracle or fingerprint mismatch",
            })

    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    exit_code = 0 if passed == EXPECTED_TOTAL else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR1",
        "execution_boundary": "[ON-TILE SILICON]",
        "evidence_class": "BIT_EXACT_PHYSICAL_SILICON",
        "child_pid": os.getpid(),
        "execution_nonce": os.environ.get("PQC_EXECUTION_NONCE", ""),
        "started_at": started_at,
        "ended_at": ended_at,
        "cases_selected": EXPECTED_TOTAL,
        "cases_executed": len(case_results),
        "exit_code": exit_code,
        "artifact": artifact_info,
        "device": device_info,
        "dispatch": {
            "physical_dispatches": completed,
            "completed": completed == EXPECTED_TOTAL,
        },
        "cases": case_results,
        "test_buffers": test_buffers,
    }

    print(RESULT_START_MARKER)
    print(json.dumps(record, indent=2))
    print(RESULT_END_MARKER)

    print("-" * 72)
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")
    print("=" * 72)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(_run_native_gate())
