# SPDX-License-Identifier: Apache-2.0
"""Milestone DR24: RFC 9370 Multi-KEM IPsec / WireGuard VPN Co-Processor Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: IETF RFC 9370, RFC 8784, RFC 5869, WireGuard Protocol.
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

from phoenix_sdr_dsp.pqc.dr24_ipsec_wireguard_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    rfc9370_combine_on_aie2,
    wireguard_encaps_on_aie2,
    wireguard_decaps_on_aie2,
    async_rekey_on_aie2,
    ref_rfc9370_combine,
    ref_wireguard_encaps,
    ref_wireguard_decaps,
    ref_async_rekey,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR24: RFC 9370 Multi-KEM IPsec / WireGuard VPN Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr24-ipsec-wireguard)")
    print("Standards: IETF RFC 9370 / RFC 8784, WireGuard Protocol Specification")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        # Preflight probe on hardware
        test_kc = b"\x11" * 32
        test_kp = b"\x22" * 32
        test_kq = b"\x33" * 32
        test_ni = b"\x44" * 64
        rfc9370_combine_on_aie2(test_kc, test_kp, test_kq, test_ni, epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr24-ipsec-wireguard:unavailable ({type(exc).__name__}: {exc})")
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
    rng = np.random.default_rng(seed=0x24937001)

    # 1. Gate 1: RFC 9370 Multi-KEM Key Combiner (5 cases)
    print("\n--- Gate 1: RFC 9370 Multi-KEM Key Combiner (5 cases) ---")
    session_keys = []
    for i in range(5):
        case_id = f"dr24_rfc9370_comb_case_{i:03d}_sess_{i+1:02d}"
        kc = rng.bytes(32)
        kp = rng.bytes(32)
        kq = rng.bytes(32) if (i % 2 == 0) else (b"\x00" * 32)
        ninr = rng.bytes(64)
        exp_ske, exp_ska, exp_skd = ref_rfc9370_combine(kc, kp, kq, ninr)

        t_start = time.perf_counter_ns()
        try:
            act_ske, act_ska, act_skd, dt_ms = rfc9370_combine_on_aie2(kc, kp, kq, ninr, epoch=100 + i)
            ok = (act_ske == exp_ske) and (act_ska == exp_ska) and (act_skd == exp_skd)
            session_keys.append((act_ske, act_ska, act_skd))
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
            "case_label": f"RFC 9370 Combiner case {i+1}",
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
                "details": "combiner mismatch",
            })

    # 2. Gate 2: WireGuard Packet Encapsulation (5 cases)
    print("\n--- Gate 2: WireGuard Packet Encapsulation (5 cases) ---")
    encaps_packets = []
    payload_lengths = [64, 128, 512, 1024, 1420]
    for i, plen in enumerate(payload_lengths):
        case_id = f"dr24_wg_enc_case_{i:03d}_len_{plen}"
        ske, ska, _ = session_keys[i]
        seq_num = 1000 + i * 17
        pt = rng.bytes(plen)
        exp_packet = ref_wireguard_encaps(ske, ska, seq_num, pt)

        t_start = time.perf_counter_ns()
        try:
            act_packet, dt_ms = wireguard_encaps_on_aie2(ske, ska, seq_num, pt, epoch=200 + i)
            ok = (act_packet == exp_packet)
            encaps_packets.append((ske, ska, seq_num, pt, act_packet))
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
            "case_label": f"WireGuard Encaps case {i+1}",
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
                "details": "packet encaps mismatch",
            })

    # 3. Gate 3: WireGuard Packet Decapsulation & Integrity (5 cases)
    print("\n--- Gate 3: WireGuard Packet Decapsulation (5 cases) ---")
    for i in range(5):
        case_id = f"dr24_wg_dec_case_{i:03d}_valid_{i+1:02d}"
        ske, ska, exp_seq, exp_pt, packet = encaps_packets[i]

        t_start = time.perf_counter_ns()
        try:
            act_seq, act_pt, status, dt_ms = wireguard_decaps_on_aie2(ske, ska, packet, epoch=300 + i)
            ok = (status == 0) and (act_seq == exp_seq) and (act_pt == exp_pt)
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
            "case_label": f"WireGuard Decaps valid case {i+1}",
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
                "details": "decaps mismatch",
            })

    # 4. Gate 4: WireGuard Replay / Tamper Detection (5 cases)
    print("\n--- Gate 4: WireGuard Tamper Detection (5 cases) ---")
    for i in range(5):
        case_id = f"dr24_wg_tamp_case_{i:03d}_tampered_{i+1:02d}"
        ske, ska, _, _, packet = encaps_packets[i]
        tampered_pkt = bytearray(packet)
        tampered_pkt[10 + i * 2] ^= 0x5A  # Corrupt authentication tag

        t_start = time.perf_counter_ns()
        try:
            _, _, status, dt_ms = wireguard_decaps_on_aie2(ske, ska, bytes(tampered_pkt), epoch=400 + i)
            ok = (status == 2)  # Correctly rejected with auth failure status
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
            "case_label": f"WireGuard Tamper case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS (Auth Failure Rejected, {dt_ms:.2f}ms)")
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
                "details": f"tampered packet status unexpected: {status}",
            })

    # 5. Gate 5: Asynchronous Background Rekeying (5 cases)
    print("\n--- Gate 5: Asynchronous Background Rekeying (5 cases) ---")
    for i in range(5):
        case_id = f"dr24_rekey_case_{i:03d}_epoch_{i+1:02d}"
        _, _, skd = session_keys[i]
        rekey_seed = rng.bytes(32)
        exp_ske, exp_ska, exp_skd = ref_async_rekey(skd, rekey_seed)

        t_start = time.perf_counter_ns()
        try:
            act_ske, act_ska, act_skd, dt_ms = async_rekey_on_aie2(skd, rekey_seed, epoch=500 + i)
            ok = (act_ske == exp_ske) and (act_ska == exp_ska) and (act_skd == exp_skd)
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
            "case_label": f"Async Rekey case {i+1}",
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
                "details": "rekey mismatch",
            })

    expected_total = 25
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR24",
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
