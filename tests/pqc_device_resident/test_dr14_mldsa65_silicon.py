# SPDX-License-Identifier: Apache-2.0
"""Fail-closed silicon validation gate for Milestone DR14 (ML-DSA-65 Master Suite)."""
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

from phoenix_sdr_dsp.pqc import dr14_mldsa65_keygen_graph as kg_graph
from phoenix_sdr_dsp.pqc import dr14_mldsa65_sign_graph as sign_graph
from phoenix_sdr_dsp.pqc import dr14_mldsa65_verify_graph as ver_graph
from tests.pqc_device_resident.test_dr14_mldsa65 import (
    KEYGEN_CORPUS,
    KEYGEN_EXPECTED,
    SIGN_CORPUS,
    SIGN_EXPECTED,
    TOTAL_DR14_CASES,
    VERIFY_CORPUS,
    VERIFY_EXPECTED,
)

EXPECTED_TOTAL = TOTAL_DR14_CASES
RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 72)
    print("PQC DR14 - complete ML-DSA-65 (KeyGen, Sign, Verify) closure")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        kg_graph.require_hardware_runtime()
        sign_graph.require_hardware_runtime()
        ver_graph.require_hardware_runtime()
    except Exception as exc:
        print(f"Backend: dr14-mldsa65:unavailable ({type(exc).__name__}: {exc})")
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran.")
        return 2

    print(f"Backend: {kg_graph.BACKEND_LABEL}")

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
        artifact_info = kg_graph.get_kernel_artifact_info(REPO_ROOT)
    except Exception as exc:
        print(f"ERROR: failed to get kernel artifact info: {exc}")
        return 1

    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    # 1. KeyGen Gate (25 vectors)
    print("\n--- Gate 1: ML-DSA-65 KeyGen (25 vectors) ---")
    for idx, case in enumerate(KEYGEN_CORPUS):
        case_id = f"dr14_kg_case_{idx:03d}_{case.test_name}"
        exp_pk, exp_sk = KEYGEN_EXPECTED[case.test_name]
        t_case_start = time.perf_counter_ns()
        try:
            actual_pk, actual_sk = kg_graph.run_mldsa65_keygen(case.seed, request_id=case.request_id)
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:02d}/25] {case.test_name:<36} ERROR ({type(exc).__name__}: {exc})")
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
            "gate_op": "keygen",
            "case_id": case_id,
            "case_label": case.test_name,
            "test_name": case.test_name,
            "tc_id": case.tc_id,
            "request_id": case.request_id,
            "pk_hex": actual_pk.hex(),
            "sk_hex": actual_sk.hex(),
        })

        if actual_pk == exp_pk and actual_sk == exp_sk:
            passed += 1
            print(f"  [{idx+1:02d}/25] {case.test_name:<36} PASS (100% bit-exact pk & sk)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/25] {case.test_name:<36} FAIL: mismatch")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "oracle mismatch",
            })

    # 2. Sign Gate (30 vectors)
    print("\n--- Gate 2: ML-DSA-65 Sign (30 vectors) ---")
    for idx, case in enumerate(SIGN_CORPUS):
        case_id = f"dr14_sign_case_{idx:03d}_{case.test_name}"
        exp_sig = SIGN_EXPECTED[case.test_name]
        t_case_start = time.perf_counter_ns()
        try:
            actual_sig = sign_graph.run_mldsa65_sign(
                case.sk,
                case.m_or_mu,
                external_mu=case.external_mu,
                request_id=case.request_id,
            )
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:02d}/30] {case.test_name:<36} ERROR ({type(exc).__name__}: {exc})")
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
            "gate_op": "sign",
            "case_id": case_id,
            "case_label": case.test_name,
            "test_name": case.test_name,
            "tc_id": case.tc_id,
            "request_id": case.request_id,
            "sig_hex": actual_sig.hex(),
        })

        if actual_sig == exp_sig:
            passed += 1
            print(f"  [{idx+1:02d}/30] {case.test_name:<36} PASS (100% bit-exact signature)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/30] {case.test_name:<36} FAIL: signature mismatch")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": "oracle mismatch",
            })

    # 3. Verify Gate (30 vectors)
    print("\n--- Gate 3: ML-DSA-65 Verify (30 vectors) ---")
    for idx, case in enumerate(VERIFY_CORPUS):
        case_id = f"dr14_ver_case_{idx:03d}_{case.test_name}"
        exp_valid = VERIFY_EXPECTED[case.test_name]
        t_case_start = time.perf_counter_ns()
        try:
            actual_valid = ver_graph.run_mldsa65_verify(
                case.pk,
                case.sig,
                case.m_or_mu,
                external_mu=case.external_mu,
                request_id=case.request_id,
            )
        except Exception as exc:
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  [{idx+1:02d}/30] {case.test_name:<36} ERROR ({type(exc).__name__}: {exc})")
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
            "gate_op": "verify",
            "case_id": case_id,
            "case_label": case.test_name,
            "test_name": case.test_name,
            "tc_id": case.tc_id,
            "request_id": case.request_id,
            "actual_valid": actual_valid,
            "expected_valid": exp_valid,
        })

        if actual_valid == exp_valid:
            passed += 1
            verdict_str = "VALID (Accepted)" if actual_valid else "INVALID (Rejected)"
            print(f"  [{idx+1:02d}/30] {case.test_name:<36} PASS ({verdict_str})")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            print(f"  [{idx+1:02d}/30] {case.test_name:<36} FAIL: verdict mismatch")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": f"verdict mismatch (got {actual_valid}, expected {exp_valid})",
            })

    status_str = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    exit_code = 0 if passed == EXPECTED_TOTAL else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR14",
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
