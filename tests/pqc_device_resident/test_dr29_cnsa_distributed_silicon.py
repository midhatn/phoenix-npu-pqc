# SPDX-License-Identifier: Apache-2.0
"""Milestone DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: NSA CNSA 2.0 Suite, FIPS 203 (ML-KEM-1024), FIPS 204 (ML-DSA-87).
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

from phoenix_sdr_dsp.pqc.dr29_cnsa_distributed_graph import (
    BACKEND_LABEL,
    CNSA_ALGO_MLDSA87,
    CNSA_ALGO_MLKEM1024,
    get_kernel_artifact_info,
    query_partition_info_on_aie2,
    compute_row_accum_on_aie2,
    aggregate_cluster_on_aie2,
    ref_compute_partition_info,
    ref_compute_row_accum,
    ref_aggregate_cluster,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR29: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr29-cnsa-distributed)")
    print("Algorithms: ML-KEM-1024 (k=4) & ML-DSA-87 (k=8, l=7, 56 polynomials)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x29292929)

    # Preflight probe on hardware
    try:
        query_partition_info_on_aie2(CNSA_ALGO_MLDSA87, tile_index=0, epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr29-cnsa-distributed:unavailable ({type(exc).__name__}: {exc})")
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

    # 1. Gate 1: Cluster Memory Partition Queries (8 cases: 4 for ML-DSA, 4 for ML-KEM)
    print("\n--- Gate 1: Cluster Memory Partition Queries (8 cases) ---")
    partition_targets = [
        (CNSA_ALGO_MLDSA87,   0, "mldsa87_tile_0"),
        (CNSA_ALGO_MLDSA87,   1, "mldsa87_tile_1"),
        (CNSA_ALGO_MLDSA87,   2, "mldsa87_tile_2"),
        (CNSA_ALGO_MLDSA87,   3, "mldsa87_tile_3"),
        (CNSA_ALGO_MLKEM1024, 0, "mlkem1024_tile_0"),
        (CNSA_ALGO_MLKEM1024, 1, "mlkem1024_tile_1"),
        (CNSA_ALGO_MLKEM1024, 2, "mlkem1024_tile_2"),
        (CNSA_ALGO_MLKEM1024, 3, "mlkem1024_tile_3"),
    ]
    for i, (algo, t_idx, label) in enumerate(partition_targets):
        case_id = f"dr29_part_case_{i:03d}_{label}"
        exp_info = ref_compute_partition_info(algo, t_idx, num_tiles=4)

        t_start = time.perf_counter_ns()
        try:
            act_info, dt_ms = query_partition_info_on_aie2(algo, t_idx, num_tiles=4, epoch=100 + i)
            ok = (act_info == exp_info) and act_info["is_under_44kb_bound"]
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"Cluster Partition case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms:.2f}ms, {act_info['total_sram_kb']}KB <= 44KB)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "partition mismatch",
            })

    # 2. Gate 2: ML-DSA-87 Distributed Row Accumulation (6 cases)
    print("\n--- Gate 2: ML-DSA-87 Distributed Row Accumulation (6 cases) ---")
    for i in range(6):
        case_id = f"dr29_mldsa_row_case_{i:03d}"
        m = rng.integers(0, 8380417, size=(7, 256), dtype=np.uint32)
        s = rng.integers(0, 8380417, size=(7, 256), dtype=np.uint32)
        exp_accum = ref_compute_row_accum(CNSA_ALGO_MLDSA87, m, s)

        t_start = time.perf_counter_ns()
        try:
            act_accum, dt_ms = compute_row_accum_on_aie2(CNSA_ALGO_MLDSA87, m, s, epoch=200 + i)
            ok = np.array_equal(act_accum, exp_accum)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"ML-DSA Row Accum case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "ML-DSA row accumulator mismatch",
            })

    # 3. Gate 3: ML-KEM-1024 Distributed Row Accumulation (6 cases)
    print("\n--- Gate 3: ML-KEM-1024 Distributed Row Accumulation (6 cases) ---")
    for i in range(6):
        case_id = f"dr29_mlkem_row_case_{i:03d}"
        m = rng.integers(0, 3329, size=(4, 256), dtype=np.uint16)
        s = rng.integers(0, 3329, size=(4, 256), dtype=np.uint16)
        exp_accum = ref_compute_row_accum(CNSA_ALGO_MLKEM1024, m, s)

        t_start = time.perf_counter_ns()
        try:
            act_accum, dt_ms = compute_row_accum_on_aie2(CNSA_ALGO_MLKEM1024, m, s, epoch=300 + i)
            ok = np.array_equal(act_accum, exp_accum)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"ML-KEM Row Accum case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "ML-KEM row accumulator mismatch",
            })

    # 4. Gate 4: Cluster Multi-Tile Aggregation (5 cases)
    print("\n--- Gate 4: Cluster Multi-Tile Aggregation (5 cases) ---")
    for i in range(5):
        algo = CNSA_ALGO_MLDSA87 if i % 2 == 0 else CNSA_ALGO_MLKEM1024
        case_id = f"dr29_cluster_agg_case_{i:03d}_{'mldsa' if algo == CNSA_ALGO_MLDSA87 else 'mlkem'}"
        q = 8380417 if algo == CNSA_ALGO_MLDSA87 else 3329
        dtype = np.uint32 if algo == CNSA_ALGO_MLDSA87 else np.uint16
        partial_polys = [rng.integers(0, q, size=256, dtype=dtype) for _ in range(4)]
        exp_sum = ref_aggregate_cluster(algo, partial_polys)

        t_start = time.perf_counter_ns()
        try:
            act_sum, dt_ms = aggregate_cluster_on_aie2(algo, partial_polys, epoch=400 + i)
            ok = np.array_equal(act_sum, exp_sum)
        except Exception as exc:
            t_dur = time.perf_counter_ns() - t_start
            print(f"  [{completed+1:02d}/25] {case_id:<45} ERROR ({type(exc).__name__}: {exc})")
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
            "case_label": f"Cluster Aggregation case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms:.2f}ms)")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_dur,
            })
        else:
            print(f"  [{completed:02d}/25] {case_id:<45} FAIL")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_dur,
                "details": "cluster aggregation mismatch",
            })

    expected_total = 25
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR29",
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
