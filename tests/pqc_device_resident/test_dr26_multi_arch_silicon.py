# SPDX-License-Identifier: Apache-2.0
"""Milestone DR26: AMD XDNA 2 & AMD Alveo V70 Multi-Architecture Scaling Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: AMD XDNA 1 / XDNA 2 / Versal AI Core (Alveo V70) Topology Specifications.
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

from phoenix_sdr_dsp.pqc.dr26_multi_arch_graph import (
    BACKEND_LABEL,
    ARCH_PHOENIX_XDNA1,
    ARCH_STRIX_XDNA2,
    ARCH_ALVEO_V70,
    get_kernel_artifact_info,
    query_arch_topology_on_aie2,
    validate_grid_fit_on_aie2,
    partition_columns_on_aie2,
    emit_mlir_topology_on_aie2,
    ref_query_arch_topology,
    ref_validate_grid_fit,
    ref_partition_columns,
    ref_emit_mlir_topology,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR26: AMD XDNA 2 & Alveo V70 Multi-Architecture Scaling Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr26-multi-arch)")
    print("Platforms: AMD Phoenix (20 tiles), Strix Point (32 tiles), Alveo V70 (304 tiles)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        # Preflight probe on hardware
        query_arch_topology_on_aie2(ARCH_PHOENIX_XDNA1, epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr26-multi-arch:unavailable ({type(exc).__name__}: {exc})")
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

    # 1. Gate 1: Multi-Architecture Topology Query (6 cases)
    print("\n--- Gate 1: Architecture Topology Queries (6 cases) ---")
    query_targets = [
        (ARCH_PHOENIX_XDNA1, "phoenix_xdna1_pass1"),
        (ARCH_STRIX_XDNA2,   "strix_xdna2_pass1"),
        (ARCH_ALVEO_V70,     "alveo_v70_pass1"),
        (ARCH_PHOENIX_XDNA1, "phoenix_xdna1_pass2"),
        (ARCH_STRIX_XDNA2,   "strix_xdna2_pass2"),
        (ARCH_ALVEO_V70,     "alveo_v70_pass2"),
    ]
    for i, (arch, label) in enumerate(query_targets):
        case_id = f"dr26_query_case_{i:03d}_{label}"
        exp_geom = ref_query_arch_topology(arch)

        t_start = time.perf_counter_ns()
        try:
            act_geom, dt_ms = query_arch_topology_on_aie2(arch, epoch=100 + i)
            ok = (act_geom == exp_geom)
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
            "case_label": f"Query Topology case {i+1}",
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
                "details": "topology mismatch",
            })

    # 2. Gate 2: Spatial Grid Fit Validation (6 cases)
    print("\n--- Gate 2: Spatial Grid Fit Validation (6 cases) ---")
    fit_cases = [
        (ARCH_PHOENIX_XDNA1, 4,   "phoenix_fit_4tiles"),
        (ARCH_PHOENIX_XDNA1, 24,  "phoenix_overflow_24tiles"),
        (ARCH_STRIX_XDNA2,   32,  "strix_exact_32tiles"),
        (ARCH_STRIX_XDNA2,   40,  "strix_overflow_40tiles"),
        (ARCH_ALVEO_V70,     304, "alveo_full_304tiles"),
        (ARCH_ALVEO_V70,     320, "alveo_overflow_320tiles"),
    ]
    for i, (arch, tiles, label) in enumerate(fit_cases):
        case_id = f"dr26_fit_case_{i:03d}_{label}"
        exp_ok, exp_max = ref_validate_grid_fit(arch, tiles)

        t_start = time.perf_counter_ns()
        try:
            act_ok, act_max, dt_ms = validate_grid_fit_on_aie2(arch, tiles, epoch=200 + i)
            ok = (act_ok == exp_ok) and (act_max == exp_max)
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
            "case_label": f"Validate Fit case {i+1}",
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
                "details": "grid fit mismatch",
            })

    # 3. Gate 3: Spatial Column Partitioning (6 cases)
    print("\n--- Gate 3: Spatial Column Partitioning (6 cases) ---")
    partition_cases = [
        (ARCH_PHOENIX_XDNA1, 2,  "phoenix_2instances"),
        (ARCH_PHOENIX_XDNA1, 5,  "phoenix_5instances"),
        (ARCH_STRIX_XDNA2,   4,  "strix_4instances"),
        (ARCH_STRIX_XDNA2,   8,  "strix_8instances"),
        (ARCH_ALVEO_V70,     19, "alveo_19instances"),
        (ARCH_ALVEO_V70,     38, "alveo_38instances"),
    ]
    for i, (arch, insts, label) in enumerate(partition_cases):
        case_id = f"dr26_part_case_{i:03d}_{label}"
        exp_parts = ref_partition_columns(arch, insts)

        t_start = time.perf_counter_ns()
        try:
            act_parts, dt_ms = partition_columns_on_aie2(arch, insts, epoch=300 + i)
            ok = (act_parts == exp_parts)
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
            "case_label": f"Partition Columns case {i+1}",
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
                "details": "partition mismatch",
            })

    # 4. Gate 4: Multi-Target MLIR Device Topology Synthesis (7 cases)
    print("\n--- Gate 4: Multi-Target MLIR Topology Synthesis (7 cases) ---")
    synth_targets = [
        (ARCH_PHOENIX_XDNA1, "phoenix_mlir_01"),
        (ARCH_STRIX_XDNA2,   "strix_mlir_01"),
        (ARCH_ALVEO_V70,     "alveo_mlir_01"),
        (ARCH_PHOENIX_XDNA1, "phoenix_mlir_02"),
        (ARCH_STRIX_XDNA2,   "strix_mlir_02"),
        (ARCH_ALVEO_V70,     "alveo_mlir_02"),
        (ARCH_ALVEO_V70,     "alveo_mlir_03"),
    ]
    for i, (arch, label) in enumerate(synth_targets):
        case_id = f"dr26_mlir_case_{i:03d}_{label}"
        exp_topo = ref_emit_mlir_topology(arch)

        t_start = time.perf_counter_ns()
        try:
            act_topo, dt_ms = emit_mlir_topology_on_aie2(arch, epoch=400 + i)
            ok = (act_topo == exp_topo)
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
            "case_label": f"MLIR Topology case {i+1}",
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
                "details": "MLIR topology mismatch",
            })

    expected_total = 25
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR26",
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
