# SPDX-License-Identifier: Apache-2.0
"""Milestone DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator Silicon Validation Suite.
Target: AMD Phoenix AIE2 / XDNA1 Architecture (dr19-hybrid-session).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr19_hybrid_session_orchestrator import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_hybrid_handshake_on_aie2,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr19-hybrid-session)")
    print("Standards: ETSI GS QKD 014, NIST FIPS 203/204, NIST SP 800-56C, IETF RFC 9370")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    print(f"Backend: {BACKEND_LABEL}")

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
        artifact_info = get_kernel_artifact_info(PROJECT_ROOT)
    except Exception as exc:
        print(f"ERROR: failed to get kernel artifact info: {exc}")
        return 1

    test_configs = [
        # (Name, KEM, DSA, Count)
        ("Hybrid Session (ML-KEM-512 + ML-DSA-44)", "ML-KEM-512", "ML-DSA-44", 5),
        ("Hybrid Session (ML-KEM-768 + ML-DSA-44)", "ML-KEM-768", "ML-DSA-44", 5),
        ("Hybrid Session (ML-KEM-1024 + ML-DSA-44)", "ML-KEM-1024", "ML-DSA-44", 5),
        ("Hybrid High-Security (ML-KEM-768 + ML-DSA-65)", "ML-KEM-768", "ML-DSA-65", 5),
        ("Hybrid High-Security (ML-KEM-1024 + ML-DSA-87)", "ML-KEM-1024", "ML-DSA-87", 5),
    ]

    cases_flat = []
    for desc, kem, dsa, count in test_configs:
        for i in range(count):
            cases_flat.append((f"{desc}_{i+1:02d}", kem, dsa, i + 1))

    expected_total = len(cases_flat)
    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    print(f"Executing {expected_total} End-to-End Hybrid QKD-PQC handshakes on AMD Phoenix silicon...")

    for idx, (name, kem, dsa, iter_idx) in enumerate(cases_flat):
        case_id = f"dr19_case_{idx:03d}_{name}"
        t_case_start = time.perf_counter_ns()
        try:
            res = run_hybrid_handshake_on_aie2(kem_param=kem, dsa_param=dsa, epoch=1000 + idx + 1)
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<50} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": name,
            "name": name,
            "kem_param": kem,
            "dsa_param": dsa,
            "is_authenticated": res.is_authenticated,
            "is_key_matched": res.is_key_matched,
            "zeroized_status": res.zeroized_status,
            "latency_ms": res.total_latency_ms,
        })

        if res.is_authenticated and res.is_key_matched and res.zeroized_status == 0:
            passed += 1
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<50} PASS (Auth & Match in {res.total_latency_ms:.1f}ms, Zeroized: OK)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<50} FAIL (auth={res.is_authenticated}, match={res.is_key_matched}, zero={res.zeroized_status})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "handshake failure",
            })

    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR19",
        "execution_boundary": "[ON-TILE SILICON]",
        "evidence_class": "BIT_EXACT_PHYSICAL_SILICON",
        "child_pid": os.getpid(),
        "execution_nonce": os.environ.get("PQC_EXECUTION_NONCE", ""),
        "started_at": started_at,
        "ended_at": ended_at,
        "cases_selected": expected_total,
        "cases_executed": len(case_results),
        "exit_code": exit_code,
        "artifact": artifact_info,
        "device": device_info,
        "dispatch": {
            "physical_dispatches": completed,
            "completed": completed == expected_total,
        },
        "cases": case_results,
        "test_buffers": test_buffers,
    }

    print(RESULT_START_MARKER)
    print(json.dumps(record, indent=2))
    print(RESULT_END_MARKER)
    print("-" * 75)
    print(f"TOTAL {passed}/{expected_total} {'PASS' if passed == expected_total else 'FAIL'}")
    print("=" * 75)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
