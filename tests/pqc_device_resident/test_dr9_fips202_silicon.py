# SPDX-License-Identifier: Apache-2.0
"""Fail-closed silicon validation gate for Milestone DR9 (Reusable NIST FIPS 202 NPU Service)."""
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

from phoenix_sdr_dsp.pqc import dr9_fips202_graph as graph
from tests.pqc_device_resident.test_dr9_fips202 import (
    ACVP_EXPECTED,
    PRE_SILICON_CORPUS,
)

EXPECTED_TOTAL = len(PRE_SILICON_CORPUS)
RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 72)
    print("PQC DR9 - complete Reusable NIST FIPS 202 NPU Service closure")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        graph.require_hardware_runtime()
    except Exception as exc:
        print(f"Backend: dr9-fips202:unavailable ({type(exc).__name__}: {exc})")
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
        case_id = f"dr9_case_{idx:03d}_{case.tc_id}"
        expected_digest = ACVP_EXPECTED[case.tc_id]
        t_case_start = time.perf_counter_ns()
        try:
            actual_digest = graph.run_fips202_service(
                case.func_name, case.msg, out_len=case.out_len, request_id=case.request_id
            )
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:03d}/{EXPECTED_TOTAL:03d}] {case.tc_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "func_name": case.func_name,
            "msg_hex": case.msg.hex(),
            "out_len": case.out_len,
            "request_id": case.request_id,
            "digest_hex": actual_digest.hex(),
        })

        if actual_digest == expected_digest:
            passed += 1
            if idx < 10 or idx % 20 == 0 or idx == EXPECTED_TOTAL - 1:
                print(f"  [{idx+1:03d}/{EXPECTED_TOTAL:03d}] {case.tc_id:<45} PASS")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:03d}/{EXPECTED_TOTAL:03d}] {case.tc_id:<45} FAIL: mismatch")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "oracle mismatch",
            })

    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    exit_code = 0 if passed == EXPECTED_TOTAL else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR9",
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
    sys.exit(main())
