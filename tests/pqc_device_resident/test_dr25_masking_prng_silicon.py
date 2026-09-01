# SPDX-License-Identifier: Apache-2.0
"""Milestone DR25: Higher-Order Masking & On-Chip Local PRNG Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: FIPS 202 SHAKE-128, TCHES Higher-Order Masking, NIST SP 800-90A.
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

from phoenix_sdr_dsp.pqc.dr25_masking_prng_graph import (
    BACKEND_LABEL,
    MODULUS_MLKEM,
    get_kernel_artifact_info,
    prng_expand_mask_on_aie2,
    mask_1st_order_on_aie2,
    mask_2nd_order_on_aie2,
    unmask_1st_order_on_aie2,
    unmask_2nd_order_on_aie2,
    masked_add_1st_order_on_aie2,
    sni_refresh_1st_order_on_aie2,
    sni_refresh_2nd_order_on_aie2,
    ref_prng_expand_mask,
    ref_mask_1st_order,
    ref_mask_2nd_order,
    ref_unmask_1st_order,
    ref_unmask_2nd_order,
    ref_masked_add_1st,
    ref_sni_refresh_1st,
    ref_sni_refresh_2nd,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR25: Higher-Order Masking & Local PRNG Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr25-masking-prng)")
    print("Standards: FIPS 202 SHAKE-128 / TCHES Higher-Order Masking (N=256, q=3329)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        # Preflight probe on hardware
        test_seed = b"\x55" * 32
        prng_expand_mask_on_aie2(test_seed, domain_sep=0, epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr25-masking-prng:unavailable ({type(exc).__name__}: {exc})")
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
    rng = np.random.default_rng(seed=0x250901)

    # 1. Gate 1: On-Tile FIPS 202 SHAKE-128 Local PRNG Mask Expansion (5 cases)
    print("\n--- Gate 1: On-Tile SHAKE-128 PRNG Mask Expansion (5 cases) ---")
    prng_masks = []
    for i in range(5):
        case_id = f"dr25_prng_mask_case_{i:03d}_dom_{i+1:02d}"
        seed = rng.bytes(32)
        dom = 100 + i * 7
        exp_mask = ref_prng_expand_mask(seed, dom, modulus=MODULUS_MLKEM, num_coeffs=256)

        t_start = time.perf_counter_ns()
        try:
            act_mask, dt_ms = prng_expand_mask_on_aie2(seed, dom, modulus=MODULUS_MLKEM, epoch=100 + i)
            ok = np.array_equal(act_mask, exp_mask)
            prng_masks.append(act_mask)
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
            "case_label": f"PRNG Mask Expansion case {i+1}",
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
                "details": "PRNG mask mismatch",
            })

    # 2. Gate 2: 1st-Order Polynomial Blinding & Unmasking (5 cases)
    print("\n--- Gate 2: 1st-Order Polynomial Blinding & Unmasking (5 cases) ---")
    first_order_shares = []
    for i in range(5):
        case_id = f"dr25_mask1_case_{i:03d}_split_rec_{i+1:02d}"
        s = rng.integers(0, MODULUS_MLKEM, size=256, dtype=np.uint16)
        mask = prng_masks[i]
        exp_s0, exp_s1 = ref_mask_1st_order(s, mask, MODULUS_MLKEM)

        t_start = time.perf_counter_ns()
        try:
            act_s0, act_s1, dt_ms1 = mask_1st_order_on_aie2(s, mask, MODULUS_MLKEM, epoch=200 + i)
            rec_s, dt_ms2 = unmask_1st_order_on_aie2(act_s0, act_s1, MODULUS_MLKEM, epoch=250 + i)
            ok = np.array_equal(act_s0, exp_s0) and np.array_equal(act_s1, exp_s1) and np.array_equal(rec_s, s)
            first_order_shares.append((act_s0, act_s1, s))
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
            "case_label": f"1st-Order Mask/Unmask case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms1 + dt_ms2:.2f}ms)")
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
                "details": "1st-order mask/unmask mismatch",
            })

    # 3. Gate 3: 2nd-Order Polynomial Blinding & Unmasking (5 cases)
    print("\n--- Gate 3: 2nd-Order Polynomial Blinding & Unmasking (5 cases) ---")
    second_order_shares = []
    for i in range(5):
        case_id = f"dr25_mask2_case_{i:03d}_split_rec_{i+1:02d}"
        s = rng.integers(0, MODULUS_MLKEM, size=256, dtype=np.uint16)
        mask1 = prng_masks[i]
        mask2 = prng_masks[(i + 1) % 5]
        exp_s0, exp_s1, exp_s2 = ref_mask_2nd_order(s, mask1, mask2, MODULUS_MLKEM)

        t_start = time.perf_counter_ns()
        try:
            act_s0, act_s1, act_s2, dt_ms1 = mask_2nd_order_on_aie2(s, mask1, mask2, MODULUS_MLKEM, epoch=300 + i)
            rec_s, dt_ms2 = unmask_2nd_order_on_aie2(act_s0, act_s1, act_s2, MODULUS_MLKEM, epoch=350 + i)
            ok = (
                np.array_equal(act_s0, exp_s0) and
                np.array_equal(act_s1, exp_s1) and
                np.array_equal(act_s2, exp_s2) and
                np.array_equal(rec_s, s)
            )
            second_order_shares.append((act_s0, act_s1, act_s2, s))
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
            "case_label": f"2nd-Order Mask/Unmask case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms1 + dt_ms2:.2f}ms)")
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
                "details": "2nd-order mask/unmask mismatch",
            })

    # 4. Gate 4: Component-wise Masked Polynomial Addition (5 cases)
    print("\n--- Gate 4: Component-wise Masked Polynomial Addition (5 cases) ---")
    for i in range(5):
        case_id = f"dr25_madd1_case_{i:03d}_eval_{i+1:02d}"
        a0, a1, a_orig = first_order_shares[i]
        b0, b1, b_orig = first_order_shares[(i + 1) % 5]
        exp_c0, exp_c1 = ref_masked_add_1st(a0, a1, b0, b1, MODULUS_MLKEM)
        exp_c_orig = (a_orig.astype(np.uint32) + b_orig.astype(np.uint32)) % MODULUS_MLKEM

        t_start = time.perf_counter_ns()
        try:
            act_c0, act_c1, dt_ms = masked_add_1st_order_on_aie2(a0, a1, b0, b1, MODULUS_MLKEM, epoch=400 + i)
            rec_c, _ = unmask_1st_order_on_aie2(act_c0, act_c1, MODULUS_MLKEM, epoch=450 + i)
            ok = np.array_equal(act_c0, exp_c0) and np.array_equal(act_c1, exp_c1) and np.array_equal(rec_c, exp_c_orig)
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
            "case_label": f"Masked Add case {i+1}",
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
                "details": "masked add mismatch",
            })

    # 5. Gate 5: Strong Non-Interfering (SNI) Share Refreshing (5 cases)
    print("\n--- Gate 5: Strong Non-Interfering Share Refreshing (5 cases) ---")
    for i in range(5):
        case_id = f"dr25_refresh_case_{i:03d}_order_{1 if i < 3 else 2}_{i+1:02d}"
        t_start = time.perf_counter_ns()
        try:
            if i < 3:
                # 1st-order refresh
                s0, s1, orig_s = first_order_shares[i]
                r = prng_masks[(i + 2) % 5]
                exp_out_s0, exp_out_s1 = ref_sni_refresh_1st(s0, s1, r, MODULUS_MLKEM)
                act_out_s0, act_out_s1, dt_ms = sni_refresh_1st_order_on_aie2(s0, s1, r, MODULUS_MLKEM, epoch=500 + i)
                rec_s, _ = unmask_1st_order_on_aie2(act_out_s0, act_out_s1, MODULUS_MLKEM, epoch=550 + i)
                ok = (
                    np.array_equal(act_out_s0, exp_out_s0) and
                    np.array_equal(act_out_s1, exp_out_s1) and
                    np.array_equal(rec_s, orig_s) and
                    not np.array_equal(act_out_s0, s0)  # Verify shares actually changed
                )
            else:
                # 2nd-order refresh
                s0, s1, s2, orig_s = second_order_shares[i]
                r01 = prng_masks[0]
                r02 = prng_masks[1]
                r12 = prng_masks[2]
                exp_out_s0, exp_out_s1, exp_out_s2 = ref_sni_refresh_2nd(s0, s1, s2, r01, r02, r12, MODULUS_MLKEM)
                act_out_s0, act_out_s1, act_out_s2, dt_ms = sni_refresh_2nd_order_on_aie2(
                    s0, s1, s2, r01, r02, r12, MODULUS_MLKEM, epoch=500 + i
                )
                rec_s, _ = unmask_2nd_order_on_aie2(act_out_s0, act_out_s1, act_out_s2, MODULUS_MLKEM, epoch=550 + i)
                ok = (
                    np.array_equal(act_out_s0, exp_out_s0) and
                    np.array_equal(act_out_s1, exp_out_s1) and
                    np.array_equal(act_out_s2, exp_out_s2) and
                    np.array_equal(rec_s, orig_s) and
                    not np.array_equal(act_out_s0, s0)
                )
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
            "case_label": f"SNI Refresh case {i+1}",
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
                "details": "refresh mismatch",
            })

    expected_total = 25
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR25",
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
