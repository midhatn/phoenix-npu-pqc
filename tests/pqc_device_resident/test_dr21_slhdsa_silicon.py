# SPDX-License-Identifier: Apache-2.0
"""Milestone DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) State-Free Hash-Based Signatures Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: NIST FIPS PUB 205 (August 2024).
"""
from __future__ import annotations

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

from phoenix_sdr_dsp.pqc import dr21_slhdsa_abi as abi
from phoenix_sdr_dsp.pqc.dr21_slhdsa_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    slhdsa_keygen_on_aie2,
    slhdsa_sign_on_aie2,
    slhdsa_verify_on_aie2,
    ref_slhdsa_keygen,
    ref_slhdsa_sign,
    ref_slhdsa_verify,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR21: NIST FIPS 205 (SLH-DSA / SPHINCS+) Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr21-slhdsa)")
    print("Standards: NIST FIPS PUB 205 (Stateless Hash-Based Digital Signatures)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        # Preflight probe on hardware
        test_seed = b"\x10" * 16
        test_pk_seed = b"\x20" * 16
        test_sk_prf = b"\x30" * 16
        slhdsa_keygen_on_aie2("SLH-DSA-SHAKE-128s", test_seed, test_pk_seed, test_sk_prf, epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr21-slhdsa:unavailable ({type(exc).__name__}: {exc})")
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

    # Corpus definitions for 30 deterministic cases (10 KeyGen, 10 Sign, 10 Verify)
    # 1. Gate 1: KeyGen (10 cases)
    print("\n--- Gate 1: SLH-DSA-SHAKE-128s KeyGen (10 cases) ---")
    rng = np.random.default_rng(seed=0x21505001)
    for i in range(10):
        case_id = f"dr21_kg_case_{i:03d}_seed_{i+1:02d}"
        sk_seed = rng.bytes(16)
        pk_seed = rng.bytes(16)
        sk_prf = rng.bytes(16)
        exp_pk, exp_sk = ref_slhdsa_keygen("SLH-DSA-SHAKE-128s", sk_seed, pk_seed, sk_prf)

        t_start = time.perf_counter_ns()
        try:
            act_pk, act_sk, dt_ms = slhdsa_keygen_on_aie2("SLH-DSA-SHAKE-128s", sk_seed, pk_seed, sk_prf, epoch=100 + i)
            ok = (act_pk == exp_pk) and (act_sk == exp_sk)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/30] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"KeyGen case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/30] {case_id:<45} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/30] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "oracle mismatch",
            })

    # 2. Gate 2: Sign (10 cases)
    print("\n--- Gate 2: SLH-DSA-SHAKE-128s Sign (10 cases) ---")
    keypairs = []
    for i in range(10):
        sk_seed = rng.bytes(16)
        pk_seed = rng.bytes(16)
        sk_prf = rng.bytes(16)
        pk, sk = ref_slhdsa_keygen("SLH-DSA-SHAKE-128s", sk_seed, pk_seed, sk_prf)
        keypairs.append((pk, sk))

    signatures = []
    for i in range(10):
        case_id = f"dr21_sign_case_{i:03d}_msg_{i+1:02d}"
        pk, sk = keypairs[i]
        msg = f"NIST FIPS 205 test message payload #{i+1} on AMD Phoenix AIE2".encode("utf-8")
        opt_rand = rng.bytes(16)
        exp_sig = ref_slhdsa_sign("SLH-DSA-SHAKE-128s", sk, msg, opt_rand)

        t_start = time.perf_counter_ns()
        try:
            act_sig, dt_ms = slhdsa_sign_on_aie2("SLH-DSA-SHAKE-128s", sk, msg, opt_rand, epoch=200 + i)
            ok = (act_sig == exp_sig)
            signatures.append((pk, msg, act_sig))
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/30] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"Sign case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/30] {case_id:<45} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/30] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "oracle mismatch",
            })

    # 3. Gate 3: Verify (10 cases: 5 valid, 5 negative/tampered)
    print("\n--- Gate 3: SLH-DSA-SHAKE-128s Verify (10 cases) ---")
    for i in range(5):
        # Valid signature verification
        case_id = f"dr21_ver_case_{i:03d}_valid_{i+1:02d}"
        pk, msg, sig = signatures[i]
        exp_verdict = ref_slhdsa_verify("SLH-DSA-SHAKE-128s", pk, msg, sig)

        t_start = time.perf_counter_ns()
        try:
            act_verdict, status_code, dt_ms = slhdsa_verify_on_aie2("SLH-DSA-SHAKE-128s", pk, msg, sig, epoch=300 + i)
            ok = (act_verdict is True) and (act_verdict == exp_verdict) and (status_code == 0)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/30] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"Verify valid case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/30] {case_id:<45} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/30] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "oracle mismatch",
            })

    for i in range(5):
        # Tampered negative verification
        case_id = f"dr21_ver_case_{i+5:03d}_tampered_{i+1:02d}"
        pk, msg, sig = signatures[i + 5]
        tampered_sig = bytearray(sig)
        tampered_sig[100 + i * 20] ^= 0xFF  # Corrupt signature byte
        exp_verdict = ref_slhdsa_verify("SLH-DSA-SHAKE-128s", pk, msg, bytes(tampered_sig))

        t_start = time.perf_counter_ns()
        try:
            act_verdict, status_code, dt_ms = slhdsa_verify_on_aie2("SLH-DSA-SHAKE-128s", pk, msg, bytes(tampered_sig), epoch=400 + i)
            ok = (act_verdict is False) and (act_verdict == exp_verdict)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/30] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"Verify negative case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/30] {case_id:<45} PASS (Correctly Rejected, {dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/30] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "oracle mismatch",
            })

    expected_total = 30
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR21",
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
