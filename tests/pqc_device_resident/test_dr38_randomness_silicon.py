# SPDX-License-Identifier: Apache-2.0
"""Milestone DR38: NIST SP 800-22 Randomness Statistical Battery & BSI AIS 31 Hardware Diagnostic Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Standards: NIST SP 800-22 Rev. 1a, BSI AIS 20 / AIS 31, NIST SP 800-90B.
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

from phoenix_sdr_dsp.pqc.dr38_randomness_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_EVAL_MONOBIT,
    MODE_EVAL_POKER,
    MODE_EVAL_RUNS_LONGEST,
    MODE_EVAL_SHANNON_ENTROPY,
    MODE_EVAL_FULL_BATTERY,
    MODE_EVAL_HEALTH_TEST,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_INSUFFICIENT_LEN,
    STATUS_ERR_TEST_FAILED,
    STATUS_ERR_HEALTH_FAILURE,
    DESC_TOTAL_BYTES,
    REQ_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr38_descriptor,
    pack_dr38_request,
    unpack_dr38_result,
    reference_dr38_oracle,
)
from phoenix_sdr_dsp.pqc.dr38_randomness_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr38_randomness_on_aie2,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR38: NIST SP 800-22 Randomness Battery & BSI AIS 31 Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr38-randomness-battery)")
    print("Standards: NIST SP 800-22 Rev. 1a, BSI AIS 20 / AIS 31, NIST SP 800-90B")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x38383838)

    # Preflight hardware probe
    try:
        dummy_sample = bytes([0x5A] * 128)
        run_dr38_randomness_on_aie2(
            op_mode=MODE_EVAL_MONOBIT,
            sample_bytes=dummy_sample,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr38-randomness-battery:unavailable ({type(exc).__name__}: {exc})")
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
    # Gate 1: Monobit Frequency & Population Count Accumulation (7 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 1: Monobit Frequency & Population Count (7 cases) ---")
    gate1_cases = [
        ("balanced_alternating", bytes([0xAA, 0x55] * 8192), 16384, MODE_EVAL_MONOBIT),
        ("balanced_half_words", bytes([0xF0, 0x0F] * 8192), 16384, MODE_EVAL_MONOBIT),
        ("random_prng_seed1", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_MONOBIT),
        ("random_prng_seed2", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_MONOBIT),
        ("random_prng_seed3", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_MONOBIT),
        ("sample_partial_4k", bytes(rng.integers(0, 256, size=4096, dtype=np.uint8)), 4096, MODE_EVAL_MONOBIT),
        ("sample_partial_8k", bytes(rng.integers(0, 256, size=8192, dtype=np.uint8)), 8192, MODE_EVAL_MONOBIT),
    ]

    for name, sample, slen, mode in gate1_cases:
        cid = f"dr38-gate1-monobit-{name}"
        seq = completed + 1

        desc = pack_dr38_descriptor(op_mode=mode, sample_bytes_len=slen, seq_id=seq)
        req = pack_dr38_request(sample_bytes=sample, seq_id=seq)
        exp_res = reference_dr38_oracle(req, desc)

        act_res, dt_ms = run_dr38_randomness_on_aie2(
            op_mode=mode,
            sample_bytes=sample,
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
    # Gate 2: BSI AIS 31 Test T2 Poker Chi-Square Distribution (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 2: BSI AIS 31 Test T2 Poker Test (6 cases) ---")
    gate2_cases = [
        ("qrng_reservoir_sim_0", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_POKER),
        ("qrng_reservoir_sim_1", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_POKER),
        ("qrng_reservoir_sim_2", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_POKER),
        ("flat_zero_variance_rejection", bytes([(i * 17) % 256 for i in range(16384)]), 16384, MODE_EVAL_POKER),
        ("block_8k_nibbles_a", bytes(rng.integers(0, 256, size=8192, dtype=np.uint8)), 8192, MODE_EVAL_POKER),
        ("block_8k_nibbles_b", bytes(rng.integers(0, 256, size=8192, dtype=np.uint8)), 8192, MODE_EVAL_POKER),
    ]

    for name, sample, slen, mode in gate2_cases:
        cid = f"dr38-gate2-poker-{name}"
        seq = completed + 1

        desc = pack_dr38_descriptor(op_mode=mode, sample_bytes_len=slen, seq_id=seq)
        req = pack_dr38_request(sample_bytes=sample, seq_id=seq)
        exp_res = reference_dr38_oracle(req, desc)

        act_res, dt_ms = run_dr38_randomness_on_aie2(
            op_mode=mode,
            sample_bytes=sample,
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
    # Gate 3: Runs Test & Longest Run Distribution (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 3: Runs Test & Longest Run Distribution (6 cases) ---")
    gate3_cases = [
        ("runs_eval_seed1", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384),
        ("runs_eval_seed2", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384),
        ("runs_eval_seed3", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384),
        ("longest_run_check_4k", bytes(rng.integers(0, 256, size=4096, dtype=np.uint8)), 4096),
        ("longest_run_check_8k", bytes(rng.integers(0, 256, size=8192, dtype=np.uint8)), 8192),
        ("longest_run_check_16k", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384),
    ]

    for name, sample, slen in gate3_cases:
        cid = f"dr38-gate3-runs-{name}"
        seq = completed + 1

        desc = pack_dr38_descriptor(op_mode=MODE_EVAL_RUNS_LONGEST, sample_bytes_len=slen, seq_id=seq)
        req = pack_dr38_request(sample_bytes=sample, seq_id=seq)
        exp_res = reference_dr38_oracle(req, desc)

        act_res, dt_ms = run_dr38_randomness_on_aie2(
            op_mode=MODE_EVAL_RUNS_LONGEST,
            sample_bytes=sample,
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
    # Gate 4: Continuous Health Test & Biased Fail-Closed Rejection (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 4: Continuous Health Test & Biased Stream Rejection (6 cases) ---")
    gate4_cases = [
        ("stuck_all_zeros", bytes(16384), 16384, MODE_EVAL_HEALTH_TEST),
        ("stuck_all_ones", bytes([0xFF] * 16384), 16384, MODE_EVAL_HEALTH_TEST),
        ("stuck_constant_byte", bytes([0x42] * 16384), 16384, MODE_EVAL_HEALTH_TEST),
        ("biased_stream_full_battery", bytes([0x00] * 14000 + [0xFF] * 2384), 16384, MODE_EVAL_FULL_BATTERY),
        ("full_battery_uniform_pass", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_FULL_BATTERY),
        ("shannon_entropy_pass", bytes(rng.integers(0, 256, size=16384, dtype=np.uint8)), 16384, MODE_EVAL_SHANNON_ENTROPY),
    ]

    for name, sample, slen, mode in gate4_cases:
        cid = f"dr38-gate4-health-{name}"
        seq = completed + 1

        desc = pack_dr38_descriptor(op_mode=mode, sample_bytes_len=slen, seq_id=seq)
        req = pack_dr38_request(sample_bytes=sample, seq_id=seq)
        exp_res = reference_dr38_oracle(req, desc)

        act_res, dt_ms = run_dr38_randomness_on_aie2(
            op_mode=mode,
            sample_bytes=sample,
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
        "deliverable": "DR38",
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

    print(f"\nDR38 Final Result: {passed}/{completed} cases passed ({'SUCCESS' if success else 'FAILURE'})")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
