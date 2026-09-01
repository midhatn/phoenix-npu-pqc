# SPDX-License-Identifier: Apache-2.0
"""Milestone DR28: NIST SP 800-208 / RFC 8554 LMS Stateless Verification Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: NIST SP 800-208, RFC 8554 (Leighton-Micali Signatures), IETF RATS (RFC 9334).
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr28_lms_verifier_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    verify_lms_signature_on_aie2,
    recover_lmots_leaf_on_aie2,
    merkle_path_traverse_on_aie2,
    ref_lms_generate_test_fixture,
    ref_lms_verify,
    ref_lmots_recover_leaf,
    ref_lms_traverse_path,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR28: NIST SP 800-208 / RFC 8554 LMS Stateless Verification Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr28-lms-verifier)")
    print("Standards: NIST SP 800-208, RFC 8554, RFC 9334 (AIE2 Bitstream Authentication)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x28282828)

    # Preflight probe on hardware
    try:
        dummy_I = rng.bytes(16)
        dummy_C, dummy_y, dummy_p, dummy_root = ref_lms_generate_test_fixture(
            dummy_I, 0, b"probe", rng, h=5
        )
        verify_lms_signature_on_aie2(dummy_I, dummy_root, 0, dummy_C, dummy_y, dummy_p, b"probe", epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr28-lms-verifier:unavailable ({type(exc).__name__}: {exc})")
        return 2

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

    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    # 1. Gate 1: End-to-End LMS Signature Verification (Valid Signatures, 7 cases)
    print("\n--- Gate 1: Valid LMS Bitstream Signatures (7 cases) ---")
    q_values = [0, 1, 5, 12, 19, 27, 31]
    for i, q in enumerate(q_values):
        case_id = f"dr28_valid_sig_case_{i:03d}_leaf_q_{q:02d}"
        I = rng.bytes(16)
        msg = f"AMD_AIE2_BITSTREAM_BLOCK_{i:02d}_AUTHENTICATION_PAYLOAD".encode("utf-8")
        C, y_sigs, auth_path, exp_root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)

        t_start = time.perf_counter_ns()
        try:
            is_valid, calc_root, dt_ms = verify_lms_signature_on_aie2(
                I, exp_root, q, C, y_sigs, auth_path, msg, epoch=100 + i
            )
            ok = is_valid and (calc_root == exp_root)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<50} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_dur = time.perf_counter_ns() - t_start
        completed += 1
        test_buffers.append({
            "case_id": case_id,
            "case_label": f"Valid LMS Signature case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<50} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<50} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "signature validation mismatch",
            })

    # 2. Gate 2: Tampered Bitstream Rejection (6 cases)
    print("\n--- Gate 2: Tampered Bitstream Rejection (6 cases) ---")
    for i in range(6):
        case_id = f"dr28_tamper_msg_case_{i:03d}"
        I = rng.bytes(16)
        q = (i * 5) % 32
        msg = f"GENUINE_FIRMWARE_HEADER_VERSION_{i}".encode("utf-8")
        C, y_sigs, auth_path, exp_root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)

        corrupt_msg = bytearray(msg)
        corrupt_msg[i % len(corrupt_msg)] ^= 0x55

        t_start = time.perf_counter_ns()
        try:
            is_valid, calc_root, dt_ms = verify_lms_signature_on_aie2(
                I, exp_root, q, C, y_sigs, auth_path, bytes(corrupt_msg), epoch=200 + i
            )
            # Must fail verification
            ok = (not is_valid) and (calc_root != exp_root)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<50} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_dur = time.perf_counter_ns() - t_start
        completed += 1
        test_buffers.append({
            "case_id": case_id,
            "case_label": f"Tampered Bitstream case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<50} PASS ({dt_ms:.2f}ms, REJECTED)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<50} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "tampered bitstream was not rejected",
            })

    # 3. Gate 3: Corrupted Signature Rejection (6 cases)
    print("\n--- Gate 3: Corrupted Signature Rejection (6 cases) ---")
    for i in range(6):
        case_id = f"dr28_corrupt_sig_case_{i:03d}"
        I = rng.bytes(16)
        q = (i * 3 + 2) % 32
        msg = f"GENUINE_KERNEL_PDI_SEGMENT_{i}".encode("utf-8")
        C, y_sigs, auth_path, exp_root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)

        corrupt_y = bytearray(y_sigs)
        corrupt_path = bytearray(auth_path)
        if i % 2 == 0:
            corrupt_y[i * 100] ^= 0xAA
        else:
            corrupt_path[i * 20] ^= 0xAA

        t_start = time.perf_counter_ns()
        try:
            is_valid, calc_root, dt_ms = verify_lms_signature_on_aie2(
                I, exp_root, q, C, bytes(corrupt_y), bytes(corrupt_path), msg, epoch=300 + i
            )
            ok = (not is_valid) and (calc_root != exp_root)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<50} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_dur = time.perf_counter_ns() - t_start
        completed += 1
        test_buffers.append({
            "case_id": case_id,
            "case_label": f"Corrupted Signature case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<50} PASS ({dt_ms:.2f}ms, REJECTED)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<50} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "corrupted signature was not rejected",
            })

    # 4. Gate 4: Sub-Operation Verification (6 cases: 3 leaf recovery, 3 path traversal)
    print("\n--- Gate 4: Sub-Operation Bit-Exactness (6 cases) ---")
    for i in range(3):
        case_id = f"dr28_leaf_recover_case_{i:03d}"
        I = rng.bytes(16)
        q = i * 7
        msg = f"LEAF_RECOVERY_TEST_{i}".encode("utf-8")
        C, y_sigs, auth_path, exp_root = ref_lms_generate_test_fixture(I, q, msg, rng, h=5)
        exp_leaf = ref_lmots_recover_leaf(I, q, C, y_sigs, msg)

        t_start = time.perf_counter_ns()
        try:
            act_leaf, dt_ms = recover_lmots_leaf_on_aie2(I, q, C, y_sigs, msg, epoch=400 + i)
            ok = (act_leaf == exp_leaf)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<50} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_dur = time.perf_counter_ns() - t_start
        completed += 1
        test_buffers.append({
            "case_id": case_id,
            "case_label": f"Leaf Recovery case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<50} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<50} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "leaf recovery mismatch",
            })

    for i in range(3):
        case_id = f"dr28_path_traverse_case_{i:03d}"
        I = rng.bytes(16)
        q = i * 9 + 1
        leaf_kc = rng.bytes(32)
        auth_path = rng.bytes(5 * 32)
        exp_root = ref_lms_traverse_path(I, q, leaf_kc, auth_path, h=5)

        t_start = time.perf_counter_ns()
        try:
            act_root, dt_ms = merkle_path_traverse_on_aie2(I, q, leaf_kc, auth_path, epoch=500 + i)
            ok = (act_root == exp_root)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<50} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_dur = time.perf_counter_ns() - t_start
        completed += 1
        test_buffers.append({
            "case_id": case_id,
            "case_label": f"Path Traversal case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<50} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<50} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "path traversal mismatch",
            })

    expected_total = 25
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR28",
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
