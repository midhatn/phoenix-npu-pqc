# SPDX-License-Identifier: Apache-2.0
"""Fail-closed silicon validation gate for Milestone DR11 (ML-DSA-44 KeyGen)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr11_mldsa44_keygen_graph as graph
from tests.pqc_device_resident.test_dr11_mldsa44_keygen import (
    ACVP_EXPECTED,
    PRE_SILICON_CORPUS,
)

EXPECTED_TOTAL = len(PRE_SILICON_CORPUS)
RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 72)
    print("PQC DR11 - complete ML-DSA-44 KeyGen closure")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        graph.require_hardware_runtime()
    except Exception as exc:
        print(f"Backend: dr11-mldsa44-keygen:unavailable ({type(exc).__name__}: {exc})")
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran.")
        return 2

    print(f"Backend: {graph.BACKEND_LABEL}")

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
        case_id = f"dr11_case_{idx:03d}_{case.tc_id}"
        exp_pk, exp_sk = ACVP_EXPECTED[case.tc_id]
        t_case_start = time.perf_counter_ns()
        try:
            actual_pk, actual_sk = graph.run_mldsa44_keygen(case.seed, request_id=case.request_id)
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:02d}/{EXPECTED_TOTAL:02d}] {case.tc_id:<35} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": case.tc_id,
            "tc_id": case.tc_id,
            "seed_hex": case.seed.hex(),
            "request_id": case.request_id,
            "pk_hex": actual_pk.hex(),
            "sk_hex": actual_sk.hex(),
        })

        if actual_pk == exp_pk and actual_sk == exp_sk:
            passed += 1
            print(f"  [{idx+1:02d}/{EXPECTED_TOTAL:02d}] {case.tc_id:<35} PASS (100% bit-exact pk & sk)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/{EXPECTED_TOTAL:02d}] {case.tc_id:<35} FAIL: mismatch")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "oracle mismatch",
            })

    status_str = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    exit_code = 0 if passed == EXPECTED_TOTAL else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR11",
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
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status_str}")
    print("=" * 72)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
