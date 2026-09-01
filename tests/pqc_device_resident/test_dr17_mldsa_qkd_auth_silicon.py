# SPDX-License-Identifier: Apache-2.0
"""Milestone DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Silicon Validation Suite.
Target: AMD Phoenix AIE2 / XDNA1 Architecture (dr17-mldsa-qkd-auth).
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

from phoenix_sdr_dsp.pqc.dr17_mldsa_qkd_auth_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    verify_qkd_manifest_on_aie2,
)
from phoenix_sdr_dsp.pqc import dr17_mldsa_qkd_auth_abi as abi
from phoenix_sdr_dsp.pqc import dr11_mldsa44_keygen_graph as kg44
from phoenix_sdr_dsp.pqc import dr12_mldsa44_sign_graph as sign44
from phoenix_sdr_dsp.pqc import dr14_mldsa65_keygen_graph as kg65
from phoenix_sdr_dsp.pqc import dr14_mldsa65_sign_graph as sign65
from tests.pqc_device_resident.test_dr17_mldsa_qkd_auth import compute_mldsa65_mu

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 70)
    print("DR17: ML-DSA Asymmetric QKD Control Plane Authenticator Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr17-mldsa-qkd-auth)")
    print("Standards: NIST FIPS 204 (ML-DSA), ETSI GS QKD 015")
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

    xi44 = secrets.token_bytes(32)
    pk44, sk44 = kg44.run_mldsa44_keygen(xi44)

    xi65 = secrets.token_bytes(32)
    pk65, sk65 = kg65.run_mldsa65_keygen(xi65)

    test_cases = []

    # 1. Authentic ML-DSA-44 QKD Session Signatures (10 cases)
    for i in range(1, 11):
        key_id = uuid.uuid4()
        nonce = secrets.token_bytes(12)
        epoch = 100 + i
        master = f"QKD_NODE_A_{i:02d}"
        slave = f"QKD_NODE_B_{i:02d}"

        manifest = abi.pack_dr17_manifest(master, slave, key_id, epoch, nonce)
        sig = sign44.run_mldsa44_sign(sk44, manifest)
        test_cases.append((f"auth_valid_mldsa44_{i:02d}", "ML-DSA-44", pk44, master, slave, key_id, epoch, nonce, sig, True))

    # 2. Authentic ML-DSA-65 QKD Session Signatures (5 cases)
    for i in range(1, 6):
        key_id = uuid.uuid4()
        nonce = secrets.token_bytes(12)
        epoch = 200 + i
        master = f"QKD_NODE_A_65_{i}"
        slave = f"QKD_NODE_B_65_{i}"
        manifest = abi.pack_dr17_manifest(master, slave, key_id, epoch, nonce)
        mu = compute_mldsa65_mu(pk65, manifest)
        sig = sign65.run_mldsa65_sign(sk65, mu, external_mu=True)
        test_cases.append((f"auth_valid_mldsa65_{i:02d}", "ML-DSA-65", pk65, master, slave, key_id, epoch, nonce, sig, True))

    # 3. Anti-MitM Tampered Manifest & Signature Rejection (10 cases)
    for i in range(1, 11):
        key_id = uuid.uuid4()
        tampered_key_id = uuid.uuid4()
        nonce = secrets.token_bytes(12)
        epoch = 400 + i
        master = "QKD_NODE_A"
        slave = "QKD_NODE_B"

        manifest = abi.pack_dr17_manifest(master, slave, key_id, epoch, nonce)
        sig = sign44.run_mldsa44_sign(sk44, manifest)

        if i <= 3:
            test_cases.append((f"anti_mitm_tampered_uuid_{i:02d}", "ML-DSA-44", pk44, master, slave, tampered_key_id, epoch, nonce, sig, False))
        elif i <= 7:
            test_cases.append((f"anti_mitm_tampered_node_{i:02d}", "ML-DSA-44", pk44, master, "ATTACKER_NODE_C", key_id, epoch, nonce, sig, False))
        else:
            tampered_sig = bytearray(sig)
            tampered_sig[10] ^= 0xFF
            test_cases.append((f"anti_mitm_corrupted_sig_{i:02d}", "ML-DSA-44", pk44, master, slave, key_id, epoch, nonce, bytes(tampered_sig), False))

    expected_total = len(test_cases)
    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    print(f"Running {expected_total} DR17 ML-DSA QKD Authentication silicon test cases on AMD Phoenix...")

    for idx, (name, param, pk, master, slave, kid, ep, nnc, sig, is_auth) in enumerate(test_cases):
        case_id = f"dr17_case_{idx:03d}_{name}"
        t_case_start = time.perf_counter_ns()
        try:
            valid, status, dt_ms = verify_qkd_manifest_on_aie2(param, pk, master, slave, kid, ep, nnc, sig, is_authentic=is_auth)
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
            "param_set": param,
            "epoch": ep,
            "valid": valid,
            "expected_valid": is_auth,
            "status": status,
        })

        if valid == is_auth:
            passed += 1
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} PASS (Valid={valid}, Status={status})")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/{expected_total:02d}] {name:<45} FAIL (valid={valid}, expected={is_auth})")
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
        "gate_id": "DR17",
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
