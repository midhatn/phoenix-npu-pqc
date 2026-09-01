# SPDX-License-Identifier: Apache-2.0
"""Milestone DR18: NIST SP 800-56C Dual-Key Combiner Silicon Validation Suite.
Target: AMD Phoenix AIE2 / XDNA1 Architecture (dr18-dual-key-combiner).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr18_dual_key_combiner_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    combine_keys_on_aie2,
)
from phoenix_sdr_dsp.pqc import dr18_dual_key_combiner_abi as abi
from tests.pqc_device_resident.test_dr18_dual_key_combiner import compute_ref_k_final

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 70)
    print("DR18: NIST SP 800-56C Dual-Key Combiner Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr18-dual-key-combiner)")
    print("Standards: NIST SP 800-56C Rev. 2, NIST SP 800-227, BSI TR-02102")
    print("=" * 70)

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

    test_cases = []

    # 1. Standard 256-bit Dual-Key Combination (10 cases)
    for i in range(1, 11):
        k_qkd = bytes([(i * 17 + j) % 256 for j in range(32)])
        k_pqc = bytes([(i * 31 + j) % 256 for j in range(32)])
        key_id = uuid.uuid4()
        epoch = 100 + i
        exp_k = compute_ref_k_final(k_qkd, k_pqc, key_id, epoch, 32)
        test_cases.append((f"dual_key_standard_{i:02d}", k_qkd, k_pqc, key_id, epoch, 32, exp_k))

    # 2. Dual-PRF Entropy Retention: Poisoned/Zeroed QKD (5 cases)
    for i in range(1, 6):
        k_qkd_zero = bytes(32)  # Poisoned QKD optical channel
        k_pqc = secrets.token_bytes(32)  # Valid ML-KEM secret
        key_id = uuid.uuid4()
        epoch = 200 + i
        exp_k = compute_ref_k_final(k_qkd_zero, k_pqc, key_id, epoch, 32)
        test_cases.append((f"entropy_retention_qkd_poisoned_{i:02d}", k_qkd_zero, k_pqc, key_id, epoch, 32, exp_k))

    # 3. Dual-PRF Entropy Retention: Compromised/Zeroed PQC (5 cases)
    for i in range(1, 6):
        k_qkd = secrets.token_bytes(32)  # Valid QKD secret
        k_pqc_zero = bytes(32)  # Broken PQC lattice
        key_id = uuid.uuid4()
        epoch = 300 + i
        exp_k = compute_ref_k_final(k_qkd, k_pqc_zero, key_id, epoch, 32)
        test_cases.append((f"entropy_retention_pqc_zeroed_{i:02d}", k_qkd, k_pqc_zero, key_id, epoch, 32, exp_k))

    # 4. High-Security 512-bit AES-XTS Key Extraction (5 cases)
    for i in range(1, 6):
        k_qkd = secrets.token_bytes(32)
        k_pqc = secrets.token_bytes(32)
        key_id = uuid.uuid4()
        epoch = 400 + i
        exp_k = compute_ref_k_final(k_qkd, k_pqc, key_id, epoch, 64)
        test_cases.append((f"dual_key_512bit_extraction_{i:02d}", k_qkd, k_pqc, key_id, epoch, 64, exp_k))

    expected_total = len(test_cases)
    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    print(f"Running {expected_total} DR18 NIST SP 800-56C silicon test cases on AMD Phoenix...")

    for idx, (name, k_q, k_p, kid, ep, out_l, expected_k) in enumerate(test_cases):
        case_id = f"dr18_case_{idx:03d}_{name}"
        t_case_start = time.perf_counter_ns()
        try:
            act_k, dt_ms = combine_keys_on_aie2(k_q, k_p, kid, ep, out_len=out_l)
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "epoch": ep,
            "out_len": out_l,
            "k_final_hex": act_k.hex(),
        })

        if act_k == expected_k and len(act_k) == out_l:
            passed += 1
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} PASS ({out_l*8}b Matched in {dt_ms:.1f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} FAIL: mismatch")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "oracle mismatch",
            })

    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR18",
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
    print("-" * 70)
    print(f"TOTAL {passed}/{expected_total} {'PASS' if passed == expected_total else 'FAIL'}")
    print("=" * 70)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
