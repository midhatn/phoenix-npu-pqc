# SPDX-License-Identifier: Apache-2.0
"""Milestone DR39: dudect Side-Channel Timing & TVLA Constant-Time Diagnostic Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Standards: NIST SP 800-140F, ISO/IEC 17825:2016/2024, Reparaz et al. (DATE 2017).
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import struct
import sys
import time
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr39_dudect_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_BENCH_CONSTANT_TIME_SELECT,
    MODE_BENCH_VARIABLE_TIME_BRANCH,
    MODE_BENCH_MONTGOMERY_REDUCTION,
    MODE_BENCH_POLYNOMIAL_ADD_SUB,
    MODE_BENCH_VARIABLE_TIME_EARLY_EXIT,
    MODE_BENCH_FULL_SUITE,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_INSUFFICIENT_LEN,
    STATUS_ERR_TIMING_LEAKAGE,
    STATUS_ERR_PARAM_OUT_OF_BOUNDS,
    DESC_TOTAL_BYTES,
    REQ_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    DUDECT_T_THRESHOLD,
    pack_dr39_descriptor,
    pack_dr39_request,
    unpack_dr39_result,
    reference_dr39_oracle,
)
from phoenix_sdr_dsp.pqc.dr39_dudect_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr39_dudect_on_aie2,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR39: dudect Side-Channel Timing & TVLA Diagnostic Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr39-dudect-tvla)")
    print("Standards: NIST SP 800-140F, ISO/IEC 17825:2016/2024, Reparaz et al. (DATE 2017)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x39393939)

    # Preflight hardware probe
    try:
        run_dr39_dudect_on_aie2(
            op_mode=MODE_BENCH_CONSTANT_TIME_SELECT,
            num_trials=20,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr39-dudect-tvla:unavailable ({type(exc).__name__}: {exc})")
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

    # -------------------------------------------------------------------------
    # Gate 1: Constant-Time Selection & Bitwise Multiplexer (7 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 1: Constant-Time Selection & Bitwise Multiplexer (7 cases) ---")
    gate1_cases = [
        ("all_zeros_vs_all_ones", bytes(32), bytes([0xFF] * 32), 500),
        ("alternating_patterns", bytes([0xAA] * 32), bytes([0x55] * 32), 500),
        ("random_seeds_a", bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 250),
        ("random_seeds_b", bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 500),
        ("random_seeds_c", bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1000),
        ("partial_trials_100", bytes([0x12] * 32), bytes([0x34] * 32), 100),
        ("partial_trials_300", bytes([0x56] * 32), bytes([0x78] * 32), 300),
    ]

    for name, s0, s1, trials in gate1_cases:
        cid = f"dr39-gate1-cmov-{name}"
        seq = completed + 1

        desc = pack_dr39_descriptor(op_mode=MODE_BENCH_CONSTANT_TIME_SELECT, num_trials=trials, seq_id=seq)
        req = pack_dr39_request(class0_seed=s0, class1_seed=s1, seq_id=seq)
        exp_res = reference_dr39_oracle(req, desc)

        act_res, dt_ms = run_dr39_dudect_on_aie2(
            op_mode=MODE_BENCH_CONSTANT_TIME_SELECT,
            num_trials=trials,
            class0_seed=s0,
            class1_seed=s1,
            seq_id=seq,
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

    # -------------------------------------------------------------------------
    # Gate 2: Constant-Time Modular & Vector Polynomial Arithmetic (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 2: Constant-Time Modular & Vector Polynomial Arithmetic (6 cases) ---")
    gate2_cases = [
        ("montgomery_small_vs_large", MODE_BENCH_MONTGOMERY_REDUCTION, bytes(32), bytes([0x0D, 0x05] * 16), 500),
        ("montgomery_random_500", MODE_BENCH_MONTGOMERY_REDUCTION, bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 500),
        ("montgomery_random_1000", MODE_BENCH_MONTGOMERY_REDUCTION, bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1000),
        ("poly_add_uniform_250", MODE_BENCH_POLYNOMIAL_ADD_SUB, bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 250),
        ("poly_add_uniform_500", MODE_BENCH_POLYNOMIAL_ADD_SUB, bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 500),
        ("poly_add_extreme_500", MODE_BENCH_POLYNOMIAL_ADD_SUB, bytes(32), bytes([0xFF] * 32), 500),
    ]

    for name, mode, s0, s1, trials in gate2_cases:
        cid = f"dr39-gate2-arith-{name}"
        seq = completed + 1

        desc = pack_dr39_descriptor(op_mode=mode, num_trials=trials, seq_id=seq)
        req = pack_dr39_request(class0_seed=s0, class1_seed=s1, seq_id=seq)
        exp_res = reference_dr39_oracle(req, desc)

        act_res, dt_ms = run_dr39_dudect_on_aie2(
            op_mode=mode,
            num_trials=trials,
            class0_seed=s0,
            class1_seed=s1,
            seq_id=seq,
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

    # -------------------------------------------------------------------------
    # Gate 3: Leaky Variable-Time Microarchitectures & Early-Exit Detection (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 3: Leaky Variable-Time Microarchitectures & Early-Exit Detection (6 cases) ---")
    gate3_cases = [
        ("vt_branch_leakage_250", MODE_BENCH_VARIABLE_TIME_BRANCH, 250),
        ("vt_branch_leakage_500", MODE_BENCH_VARIABLE_TIME_BRANCH, 500),
        ("vt_branch_leakage_1000", MODE_BENCH_VARIABLE_TIME_BRANCH, 1000),
        ("vt_early_exit_byte0", MODE_BENCH_VARIABLE_TIME_EARLY_EXIT, 250),
        ("vt_early_exit_byte128", MODE_BENCH_VARIABLE_TIME_EARLY_EXIT, 500),
        ("vt_early_exit_1000", MODE_BENCH_VARIABLE_TIME_EARLY_EXIT, 1000),
    ]

    for name, mode, trials in gate3_cases:
        cid = f"dr39-gate3-leaky-{name}"
        seq = completed + 1

        desc = pack_dr39_descriptor(op_mode=mode, num_trials=trials, seq_id=seq)
        req = pack_dr39_request(seq_id=seq)
        exp_res = reference_dr39_oracle(req, desc)

        act_res, dt_ms = run_dr39_dudect_on_aie2(
            op_mode=mode,
            num_trials=trials,
            seq_id=seq,
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

    # -------------------------------------------------------------------------
    # Gate 4: Comprehensive dudect TVLA Battery & Fail-Closed Boundaries (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 4: Comprehensive dudect TVLA Battery & Fail-Closed Boundaries (6 cases) ---")
    gate4_cases = [
        ("full_suite_pass_250", MODE_BENCH_FULL_SUITE, 250),
        ("full_suite_pass_500", MODE_BENCH_FULL_SUITE, 500),
        ("full_suite_pass_1000", MODE_BENCH_FULL_SUITE, 1000),
        ("insufficient_trials_rejection", MODE_BENCH_FULL_SUITE, 5),     # num_trials < 10
        ("invalid_magic_rejection", MODE_BENCH_FULL_SUITE, 500),         # Corrupted magic
        ("param_out_of_bounds_rejection", 99, 500),                      # Invalid op_mode
    ]

    for name, mode, trials in gate4_cases:
        cid = f"dr39-gate4-boundary-{name}"
        seq = completed + 1

        if name == "invalid_magic_rejection":
            bad_desc = bytearray(pack_dr39_descriptor(op_mode=mode, num_trials=trials, seq_id=seq))
            struct.pack_into("<I", bad_desc, 0, 0xBAD00003)
            desc = bytes(bad_desc)
        else:
            desc = pack_dr39_descriptor(op_mode=mode, num_trials=trials, seq_id=seq)

        req = pack_dr39_request(seq_id=seq)
        exp_res = reference_dr39_oracle(req, desc)

        # Dispatch with custom descriptor when testing invalid magic
        if name == "invalid_magic_rejection":
            from phoenix_sdr_dsp.pqc.dr39_dudect_graph import _dispatch_dr39
            act_res, dt_ms = _dispatch_dr39(desc, req)
        else:
            act_res, dt_ms = run_dr39_dudect_on_aie2(
                op_mode=mode,
                num_trials=trials,
                seq_id=seq,
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

    completed_at = datetime.now(timezone.utc).isoformat()
    success = (completed == 25 and passed == 25)

    result_payload = {
        "deliverable": "DR39",
        "backend": BACKEND_LABEL,
        "status": "PASS" if success else "FAIL",
        "started_at": started_at,
        "completed_at": completed_at,
        "cases_selected": 25,
        "cases_executed": completed,
        "cases_matching": passed,
        "cases_failing": completed - passed,
        "cases_skipped": 0,
        "cases_xfailed": 0,
        "device_info": device_info,
        "artifact_info": artifact_info,
        "case_results": case_results,
        "test_buffers": test_buffers,
    }

    print("\n" + RESULT_START_MARKER)
    print(json.dumps(result_payload, indent=2))
    print(RESULT_END_MARKER)

    print(f"\nDR39 Final Result: {passed}/{completed} cases passed ({'SUCCESS' if success else 'FAILURE'})")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
