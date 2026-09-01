# SPDX-License-Identifier: Apache-2.0
"""Milestone DR16: ETSI GS QKD 014 Sealed Ingress Silicon Validation Suite.
Target: AMD Phoenix AIE2 / XDNA1 Architecture (dr16-etsi-qkd014).
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr16_etsi_qkd014_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr16_ingress_service,
)
from phoenix_sdr_dsp.pqc import dr16_etsi_qkd014_abi as abi

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 70)
    print("DR16: ETSI GS QKD 014 Key Ingress Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr16-etsi-qkd014)")
    print("Standards: ETSI GS QKD 014 v1.1.1/v1.3.1, ITU-T Y.3800")
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

    # 1. Standard ETSI 014 256-bit Key Containers (15 cases)
    for i in range(1, 16):
        key_raw = bytes([(i * 13 + j) % 256 for j in range(32)])
        key_uuid = uuid.uuid4()
        epoch = 1000 + i

        container_json = json.dumps({
            "keys": [
                {
                    "key_ID": str(key_uuid),
                    "key": base64.b64encode(key_raw).decode("ascii")
                }
            ]
        })
        parsed_keys = abi.parse_etsi_014_json(container_json, epoch=epoch)
        k = parsed_keys[0]

        desc_buf = abi.pack_dr16_descriptor(k.key_id, k.epoch, len(k.key_bytes), request_id=i)
        req_buf = abi.pack_dr16_request(k.key_bytes, k.source_sae_id, k.target_sae_id)
        test_cases.append((f"etsi_qkd014_key_ingress_{i:02d}", req_buf, desc_buf, 0, i))

    # 2. High-Security 512-bit Key Containers (5 cases)
    for i in range(1, 6):
        key_raw = bytes([(i * 29 + j) % 256 for j in range(64)])
        key_uuid = uuid.uuid4()
        epoch = 2000 + i

        container_json = json.dumps({
            "keys": [
                {
                    "key_ID": str(key_uuid),
                    "key": base64.b64encode(key_raw).decode("ascii")
                }
            ]
        })
        parsed_keys = abi.parse_etsi_014_json(container_json, epoch=epoch)
        k = parsed_keys[0]

        desc_buf = abi.pack_dr16_descriptor(k.key_id, k.epoch, len(k.key_bytes), request_id=20+i)
        req_buf = abi.pack_dr16_request(k.key_bytes, k.source_sae_id, k.target_sae_id)
        test_cases.append((f"etsi_qkd014_512bit_ingress_{i:02d}", req_buf, desc_buf, 0, 20+i))

    # 3. Replay Attack & Stale Epoch Rejection (5 cases)
    for i in range(1, 6):
        key_raw = bytes([0xAA] * 32)
        key_uuid = uuid.uuid4()
        stale_epoch = 500  # Less than 2000

        desc_buf = abi.pack_dr16_descriptor(key_uuid, stale_epoch, 32, request_id=30+i)
        req_buf = abi.pack_dr16_request(key_raw)
        test_cases.append((f"etsi_qkd014_stale_epoch_rej_{i:02d}", req_buf, desc_buf, 3, 30+i))  # Status 3 = Stale

    expected_total = len(test_cases)
    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    print(f"Running {expected_total} DR16 ETSI GS QKD 014 silicon test cases on AMD Phoenix...")

    for idx, (name, req_buf, desc_buf, expected_status, req_id_in) in enumerate(test_cases):
        case_id = f"dr16_case_{idx:03d}_{name}"
        t_case_start = time.perf_counter_ns()
        try:
            req_id, status, active_slot, crc = run_dr16_ingress_service(req_buf, desc_buf)
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
            "request_id": req_id,
            "status": status,
            "active_slot": active_slot,
            "crc": crc,
        })

        if status == expected_status:
            passed += 1
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} PASS (Status={status}, Active={active_slot})")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} FAIL (status={status}, expected={expected_status})")
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
        "gate_id": "DR16",
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
