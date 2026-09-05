# SPDX-License-Identifier: Apache-2.0
"""Milestone DR40: Reproducible High-Throughput Hardware Benchmark Protocol & Profiling Battery Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Standards: NIST IR 8419, eBACS / SUPERCOP (Bernstein & Lange), ISO/IEC 19790:2012, ISO/IEC 24759:2017.
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

from phoenix_sdr_dsp.pqc.dr40_benchmark_abi import (
    MAGIC_HEADER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_UNSUPPORTED_MODE,
    STATUS_ERR_INVALID_BATCH,
    MODE_BENCH_NTT_BUTTERFLY,
    MODE_BENCH_KECCAK_F1600,
    MODE_BENCH_VECTOR_MAC,
    MODE_BENCH_SAMPLE_NTT,
    DESCRIPTOR_SIZE,
    REQUEST_BUFFER_SIZE,
    RESULT_BUFFER_SIZE,
    MODULUS_Q,
    BenchmarkDescriptor,
    BenchmarkResultHeader,
    compute_reference_oracle,
    calculate_benchmark_metrics,
)
from phoenix_sdr_dsp.pqc.dr40_benchmark_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr40_benchmark_on_aie2,
    NativeBackendUnavailable,
    _dispatch_dr40,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR40: High-Throughput Hardware Benchmark & Profiling Battery Silicon Suite")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr40-hardware-benchmark)")
    print("Standards: NIST IR 8419, eBACS (Bernstein & Lange), ISO/IEC 19790/24759")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x40404040)

    # Preflight hardware probe
    try:
        run_dr40_benchmark_on_aie2(
            op_mode=MODE_BENCH_NTT_BUTTERFLY,
            batch_size=1,
            warmup_iters=0,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr40-hardware-benchmark:unavailable ({type(exc).__name__}: {exc})")
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
    # Gate 1: NTT Butterfly Workload Benchmark & Scaling (7 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 1: NTT Butterfly Workload Benchmark & Scaling (7 cases) ---")
    gate1_batches = [
        (1, 0, "batch-1"),
        (2, 1, "batch-2"),
        (4, 2, "batch-4"),
        (8, 2, "batch-8"),
        (16, 4, "batch-16"),
        (32, 4, "batch-32"),
        (64, 8, "batch-64"),
    ]

    # Deterministic input polynomial for Gate 1
    poly_in = [(i * 37 + 19) % MODULUS_Q for i in range(256)]
    req_poly = bytearray(REQUEST_BUFFER_SIZE)
    for i, val in enumerate(poly_in):
        struct.pack_into("<H", req_poly, i * 2, val)
    req_poly_bytes = bytes(req_poly)

    for batch, warmup, name in gate1_batches:
        cid = f"dr40-gate1-ntt-{name}"
        seq = completed + 1

        exp_oracle = compute_reference_oracle(
            op_mode=MODE_BENCH_NTT_BUTTERFLY,
            request_bytes=req_poly_bytes,
            batch_size=batch,
            warmup_iters=warmup,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr40_benchmark_on_aie2(
            op_mode=MODE_BENCH_NTT_BUTTERFLY,
            batch_size=batch,
            warmup_iters=warmup,
            request_bytes=req_poly_bytes,
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
    # Gate 2: Keccak-f[1600] Permutation Benchmark (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 2: Keccak-f[1600] Permutation Benchmark (6 cases) ---")
    gate2_rounds = [
        (1, 4, "1-round"),
        (2, 4, "2-rounds"),
        (4, 4, "4-rounds"),
        (8, 4, "8-rounds"),
        (16, 4, "16-rounds"),
        (24, 8, "24-rounds"),
    ]

    keccak_state_in = [(i * 0xFEDCBA9876543210 + 0x13579BDF02468ACE) & 0xFFFFFFFFFFFFFFFF for i in range(25)]
    req_keccak = bytearray(REQUEST_BUFFER_SIZE)
    for i, val in enumerate(keccak_state_in):
        struct.pack_into("<Q", req_keccak, i * 8, val)
    req_keccak_bytes = bytes(req_keccak)

    for rounds, batch, name in gate2_rounds:
        cid = f"dr40-gate2-keccak-{name}"
        seq = completed + 1

        exp_oracle = compute_reference_oracle(
            op_mode=MODE_BENCH_KECCAK_F1600,
            request_bytes=req_keccak_bytes,
            batch_size=batch,
            warmup_iters=1,
            param_0=rounds,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr40_benchmark_on_aie2(
            op_mode=MODE_BENCH_KECCAK_F1600,
            batch_size=batch,
            warmup_iters=1,
            request_bytes=req_keccak_bytes,
            param_0=rounds,
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
    # Gate 3: Vector Polynomial Multiply-Accumulate Benchmark (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 3: Vector Polynomial Multiply-Accumulate Benchmark (6 cases) ---")
    gate3_batches = [
        (2, "batch-2"),
        (4, "batch-4"),
        (8, "batch-8"),
        (16, "batch-16"),
        (32, "batch-32"),
        (64, "batch-64"),
    ]

    poly_a = [(i * 23 + 17) % MODULUS_Q for i in range(256)]
    poly_b = [(i * 41 + 29) % MODULUS_Q for i in range(256)]
    req_mac = bytearray(REQUEST_BUFFER_SIZE)
    for i in range(256):
        struct.pack_into("<H", req_mac, i * 2, poly_a[i])
        struct.pack_into("<H", req_mac, 512 + i * 2, poly_b[i])
    req_mac_bytes = bytes(req_mac)

    for batch, name in gate3_batches:
        cid = f"dr40-gate3-mac-{name}"
        seq = completed + 1

        exp_oracle = compute_reference_oracle(
            op_mode=MODE_BENCH_VECTOR_MAC,
            request_bytes=req_mac_bytes,
            batch_size=batch,
            warmup_iters=2,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr40_benchmark_on_aie2(
            op_mode=MODE_BENCH_VECTOR_MAC,
            batch_size=batch,
            warmup_iters=2,
            request_bytes=req_mac_bytes,
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
    # Gate 4: Profiling Battery Stability & Boundary Validation (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 4: Profiling Battery Stability & Boundary Validation (6 cases) ---")
    seed_sample = bytes([(i * 53 + 7) & 0xFF for i in range(768)])
    req_sample = seed_sample + bytes(REQUEST_BUFFER_SIZE - len(seed_sample))

    # Case 20: Sample NTT batch 8
    cid20 = "dr40-gate4-sample-ntt-batch-8"
    seq = completed + 1
    exp_o20 = compute_reference_oracle(MODE_BENCH_SAMPLE_NTT, req_sample, batch_size=8, warmup_iters=2)
    exp_res20 = exp_o20.pack()
    act_res20, dt_ms20 = run_dr40_benchmark_on_aie2(MODE_BENCH_SAMPLE_NTT, batch_size=8, warmup_iters=2, request_bytes=req_sample, seq_id=seq)
    m20 = (act_res20 == exp_res20)
    completed += 1; passed += int(m20)
    case_results.append({"case_id": cid20, "status": "PASS" if m20 else "FAIL", "runtime_ms": round(dt_ms20, 3)})
    test_buffers.append({"case_id": cid20, "expected_hex": exp_res20[:64].hex(), "actual_hex": act_res20[:64].hex()})
    print(f"  {cid20}: {'PASS' if m20 else 'FAIL'} ({dt_ms20:.2f} ms)")

    # Case 21: Sample NTT batch 16
    cid21 = "dr40-gate4-sample-ntt-batch-16"
    seq = completed + 1
    exp_o21 = compute_reference_oracle(MODE_BENCH_SAMPLE_NTT, req_sample, batch_size=16, warmup_iters=4)
    exp_res21 = exp_o21.pack()
    act_res21, dt_ms21 = run_dr40_benchmark_on_aie2(MODE_BENCH_SAMPLE_NTT, batch_size=16, warmup_iters=4, request_bytes=req_sample, seq_id=seq)
    m21 = (act_res21 == exp_res21)
    completed += 1; passed += int(m21)
    case_results.append({"case_id": cid21, "status": "PASS" if m21 else "FAIL", "runtime_ms": round(dt_ms21, 3)})
    test_buffers.append({"case_id": cid21, "expected_hex": exp_res21[:64].hex(), "actual_hex": act_res21[:64].hex()})
    print(f"  {cid21}: {'PASS' if m21 else 'FAIL'} ({dt_ms21:.2f} ms)")

    # Case 22: Repeatability & Stability Profiling (5 dispatches)
    cid22 = "dr40-gate4-repeatability-stability"
    durations_us: list[float] = []
    stability_pass = True
    for rep in range(5):
        t_start = time.perf_counter_ns()
        act_res_rep, _ = run_dr40_benchmark_on_aie2(MODE_BENCH_NTT_BUTTERFLY, batch_size=16, warmup_iters=2, request_bytes=req_poly_bytes)
        t_end = time.perf_counter_ns()
        durations_us.append((t_end - t_start) / 1000.0)
        hdr = BenchmarkResultHeader.unpack(act_res_rep)
        if hdr.status != STATUS_SUCCESS:
            stability_pass = False

    metrics = calculate_benchmark_metrics(MODE_BENCH_NTT_BUTTERFLY, batch_size=16, durations_us=durations_us)
    # Stability criterion: CV < 30% across physical dispatches
    m22 = stability_pass and (metrics.cv_percent < 30.0)
    completed += 1; passed += int(m22)
    case_results.append({"case_id": cid22, "status": "PASS" if m22 else "FAIL", "runtime_ms": round(metrics.mean_us / 1000.0, 3)})
    test_buffers.append({"case_id": cid22, "expected_hex": f"cv_target<30.0%_mean={metrics.mean_us:.1f}us", "actual_hex": f"cv={metrics.cv_percent:.2f}%_ops_sec={metrics.ops_per_second:.0f}"})
    print(f"  {cid22}: {'PASS' if m22 else 'FAIL'} (CV={metrics.cv_percent:.2f}%, {metrics.ops_per_second:.0f} ops/s)")

    # Case 23: Boundary - Invalid Magic Header Rejection
    cid23 = "dr40-gate4-boundary-invalid-magic"
    bad_magic_desc = BenchmarkDescriptor(
        op_mode=MODE_BENCH_NTT_BUTTERFLY,
        batch_size=8,
        magic=0xDEADBEEF,
    ).pack()
    act_bad_magic, dt_ms23 = _dispatch_dr40(bad_magic_desc, req_poly_bytes)
    hdr23 = BenchmarkResultHeader.unpack(act_bad_magic)
    m23 = (hdr23.status == STATUS_ERR_INVALID_MAGIC)
    completed += 1; passed += int(m23)
    case_results.append({"case_id": cid23, "status": "PASS" if m23 else "FAIL", "runtime_ms": round(dt_ms23, 3)})
    test_buffers.append({"case_id": cid23, "expected_hex": hex(STATUS_ERR_INVALID_MAGIC), "actual_hex": hex(hdr23.status)})
    print(f"  {cid23}: {'PASS' if m23 else 'FAIL'} (status={hex(hdr23.status)})")

    # Case 24: Boundary - Zero Batch Size Rejection
    cid24 = "dr40-gate4-boundary-zero-batch"
    zero_batch_desc = BenchmarkDescriptor(
        op_mode=MODE_BENCH_NTT_BUTTERFLY,
        batch_size=0,
    ).pack()
    act_zero_batch, dt_ms24 = _dispatch_dr40(zero_batch_desc, req_poly_bytes)
    hdr24 = BenchmarkResultHeader.unpack(act_zero_batch)
    m24 = (hdr24.status == STATUS_ERR_INVALID_BATCH)
    completed += 1; passed += int(m24)
    case_results.append({"case_id": cid24, "status": "PASS" if m24 else "FAIL", "runtime_ms": round(dt_ms24, 3)})
    test_buffers.append({"case_id": cid24, "expected_hex": hex(STATUS_ERR_INVALID_BATCH), "actual_hex": hex(hdr24.status)})
    print(f"  {cid24}: {'PASS' if m24 else 'FAIL'} (status={hex(hdr24.status)})")

    # Case 25: Boundary - Unsupported Mode Rejection
    cid25 = "dr40-gate4-boundary-unsupported-mode"
    unsupported_desc = BenchmarkDescriptor(
        op_mode=0x8888,
        batch_size=8,
    ).pack()
    act_unsupported, dt_ms25 = _dispatch_dr40(unsupported_desc, req_poly_bytes)
    hdr25 = BenchmarkResultHeader.unpack(act_unsupported)
    m25 = (hdr25.status == STATUS_ERR_UNSUPPORTED_MODE)
    completed += 1; passed += int(m25)
    case_results.append({"case_id": cid25, "status": "PASS" if m25 else "FAIL", "runtime_ms": round(dt_ms25, 3)})
    test_buffers.append({"case_id": cid25, "expected_hex": hex(STATUS_ERR_UNSUPPORTED_MODE), "actual_hex": hex(hdr25.status)})
    print(f"  {cid25}: {'PASS' if m25 else 'FAIL'} (status={hex(hdr25.status)})")

    completed_at = datetime.now(timezone.utc).isoformat()
    success = (completed == 25 and passed == 25)

    result_payload = {
        "deliverable": "DR40",
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

    print(f"\nDR40 Final Result: {passed}/{completed} cases passed ({'SUCCESS' if success else 'FAILURE'})")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
