# SPDX-License-Identifier: Apache-2.0
"""Milestone DR33: Physical Side-Channel Power/EM Trace Acquisition & TVLA Framework Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: ISO/IEC 17825:2016 / 2024, NIST SP 800-140F, NIST NIAT TVLA Methodology.
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

from phoenix_sdr_dsp.pqc.dr33_side_channel_tvla_abi import (
    MAGIC_DESC_DR33,
    MODE_TVLA_TRIGGER_EMIT,
    MODE_TVLA_FIXED_VS_RANDOM,
    MODE_TVLA_CALIBRATION_PULSE,
    MODE_TVLA_MASKED_PIPELINE,
    TARGET_ML_KEM_NTT,
    TARGET_ML_DSA_POLY,
    TARGET_KECCAK_F1600,
    TARGET_MASKED_MULT,
    REQ_TOTAL_BYTES,
    DESC_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr33_descriptor,
    pack_dr33_request,
    unpack_dr33_result,
    reference_dr33_oracle,
)
from phoenix_sdr_dsp.pqc.dr33_side_channel_tvla_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr33_tvla_trigger_on_aie2,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR33: Physical Side-Channel Power/EM Trace Acquisition & TVLA Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr33-tvla-trigger)")
    print("Standards: ISO/IEC 17825, NIST SP 800-140F, NIST NIAT TVLA")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x33333333)

    # Preflight probe on hardware
    try:
        dummy_in = bytes(512)
        run_dr33_tvla_trigger_on_aie2(
            MODE_TVLA_TRIGGER_EMIT, TARGET_ML_KEM_NTT, 1, dummy_in
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr33-tvla-trigger:unavailable ({type(exc).__name__}: {exc})")
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

    # 1. Gate 1: ML-KEM NTT Polynomial Workload Under Side-Channel Trigger (7 cases)
    print("\n--- Gate 1: ML-KEM NTT Polynomial Workload (7 cases) ---")
    gate1_cases = [
        ("zeros", bytes(512)),
        ("ones", bytes([1] * 512)),
        ("alternating", bytes([0xAA, 0x55] * 256)),
        ("ramp", bytes([i % 256 for i in range(512)])),
        ("random_a", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_b", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_c", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
    ]

    for name, in_data in gate1_cases:
        cid = f"dr33-gate1-mlkem-ntt-{name}"
        seq = completed + 1
        desc = pack_dr33_descriptor(
            op_mode=MODE_TVLA_TRIGGER_EMIT,
            target_algo=TARGET_ML_KEM_NTT,
            seq_id=seq,
            input_len=len(in_data),
        )
        req = pack_dr33_request(in_data, seq_id=seq, target_algo=TARGET_ML_KEM_NTT)
        exp_res = reference_dr33_oracle(desc, req)

        act_res, dt_ms = run_dr33_tvla_trigger_on_aie2(
            op_mode=MODE_TVLA_TRIGGER_EMIT,
            target_algo=TARGET_ML_KEM_NTT,
            seq_id=seq,
            input_coeffs_or_seed=in_data,
        )

        match = (act_res == exp_res)
        completed += 1
        if match:
            passed += 1

        case_results.append({
            "case_id": cid,
            "status": "PASS" if match else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_res[:64].hex(),
            "actual_hex": act_res[:64].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    # 2. Gate 2: ML-DSA Polynomial Arithmetic Under Side-Channel Trigger (6 cases)
    print("\n--- Gate 2: ML-DSA Polynomial Arithmetic (6 cases) ---")
    gate2_cases = [
        ("zeros", bytes(512)),
        ("q_mod_boundary", bytes([0xFF, 0x7F] * 256)),
        ("pattern_a", bytes([0x12, 0x34] * 256)),
        ("random_dsa_1", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_dsa_2", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_dsa_3", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
    ]

    for name, in_data in gate2_cases:
        cid = f"dr33-gate2-mldsa-poly-{name}"
        seq = completed + 1
        desc = pack_dr33_descriptor(
            op_mode=MODE_TVLA_TRIGGER_EMIT,
            target_algo=TARGET_ML_DSA_POLY,
            seq_id=seq,
            input_len=len(in_data),
        )
        req = pack_dr33_request(in_data, seq_id=seq, target_algo=TARGET_ML_DSA_POLY)
        exp_res = reference_dr33_oracle(desc, req)

        act_res, dt_ms = run_dr33_tvla_trigger_on_aie2(
            op_mode=MODE_TVLA_TRIGGER_EMIT,
            target_algo=TARGET_ML_DSA_POLY,
            seq_id=seq,
            input_coeffs_or_seed=in_data,
        )

        match = (act_res == exp_res)
        completed += 1
        if match:
            passed += 1

        case_results.append({
            "case_id": cid,
            "status": "PASS" if match else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_res[:64].hex(),
            "actual_hex": act_res[:64].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    # 3. Gate 3: Masked Polynomial Multiplication Under Side-Channel Trigger (6 cases)
    print("\n--- Gate 3: Masked Polynomial Multiplication (6 cases) ---")
    gate3_cases = [
        ("unmasked_identity", bytes(512)),
        ("share_refresh_a", bytes([0x5A, 0xA5] * 256)),
        ("share_refresh_b", bytes([0xFF] * 512)),
        ("random_mask_1", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_mask_2", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_mask_3", bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
    ]

    for name, in_data in gate3_cases:
        cid = f"dr33-gate3-masked-mult-{name}"
        seq = completed + 1
        desc = pack_dr33_descriptor(
            op_mode=MODE_TVLA_MASKED_PIPELINE,
            target_algo=TARGET_MASKED_MULT,
            seq_id=seq,
            input_len=len(in_data),
        )
        req = pack_dr33_request(in_data, seq_id=seq, target_algo=TARGET_MASKED_MULT)
        exp_res = reference_dr33_oracle(desc, req)

        act_res, dt_ms = run_dr33_tvla_trigger_on_aie2(
            op_mode=MODE_TVLA_MASKED_PIPELINE,
            target_algo=TARGET_MASKED_MULT,
            seq_id=seq,
            input_coeffs_or_seed=in_data,
        )

        match = (act_res == exp_res)
        completed += 1
        if match:
            passed += 1

        case_results.append({
            "case_id": cid,
            "status": "PASS" if match else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_res[:64].hex(),
            "actual_hex": act_res[:64].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    # 4. Gate 4: TVLA Fixed-vs-Random Sequence & Calibration Pulse (6 cases)
    print("\n--- Gate 4: TVLA Fixed-vs-Random Sequence & Calibration Pulse (6 cases) ---")
    gate4_cases = [
        ("fixed_vector_pass1", MODE_TVLA_FIXED_VS_RANDOM, TARGET_ML_KEM_NTT, bytes(512)),
        ("fixed_vector_pass2", MODE_TVLA_FIXED_VS_RANDOM, TARGET_ML_KEM_NTT, bytes(512)),
        ("random_vector_pass1", MODE_TVLA_FIXED_VS_RANDOM, TARGET_ML_KEM_NTT, bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("random_vector_pass2", MODE_TVLA_FIXED_VS_RANDOM, TARGET_ML_KEM_NTT, bytes(rng.integers(0, 256, size=512, dtype=np.uint8))),
        ("calibration_pulse_a", MODE_TVLA_CALIBRATION_PULSE, TARGET_KECCAK_F1600, bytes([0x55] * 512)),
        ("calibration_pulse_b", MODE_TVLA_CALIBRATION_PULSE, TARGET_KECCAK_F1600, bytes([0xAA] * 512)),
    ]

    for name, mode, algo, in_data in gate4_cases:
        cid = f"dr33-gate4-tvla-seq-{name}"
        seq = completed + 1
        desc = pack_dr33_descriptor(
            op_mode=mode,
            target_algo=algo,
            seq_id=seq,
            input_len=len(in_data),
        )
        req = pack_dr33_request(in_data, seq_id=seq, target_algo=algo)
        exp_res = reference_dr33_oracle(desc, req)

        act_res, dt_ms = run_dr33_tvla_trigger_on_aie2(
            op_mode=mode,
            target_algo=algo,
            seq_id=seq,
            input_coeffs_or_seed=in_data,
        )

        match = (act_res == exp_res)
        completed += 1
        if match:
            passed += 1

        case_results.append({
            "case_id": cid,
            "status": "PASS" if match else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_res[:64].hex(),
            "actual_hex": act_res[:64].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    ended_at = datetime.now(timezone.utc).isoformat()

    print("\n" + "=" * 75)
    print(f"DR33 Silicon Gate Summary: {passed}/{completed} cases passed ({passed/completed*100:.1f}%)")
    print("=" * 75)

    payload = {
        "dr_id": "DR33",
        "gate_name": "dr33-tvla-trigger:silicon",
        "backend": BACKEND_LABEL,
        "device_info": device_info,
        "artifact_info": artifact_info,
        "started_at": started_at,
        "ended_at": ended_at,
        "cases_total": completed,
        "cases_passed": passed,
        "cases_failed": completed - passed,
        "case_results": case_results,
        "test_buffers": test_buffers,
    }

    print(RESULT_START_MARKER)
    print(json.dumps(payload, indent=2))
    print(RESULT_END_MARKER)

    return 0 if (passed == completed and completed == 25) else 1


if __name__ == "__main__":
    sys.exit(main())
