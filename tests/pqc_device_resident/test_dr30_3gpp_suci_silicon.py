# SPDX-License-Identifier: Apache-2.0
"""Milestone DR30: 3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: 3GPP TS 33.501 (Rel-18/19), 3GPP TR 33.841, FIPS 203 (ML-KEM-768/1024).
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

from phoenix_sdr_dsp.pqc.dr30_3gpp_suci_abi import (
    PROFILE_NULL,
    PROFILE_A_CURVE25519,
    PROFILE_C_MLKEM768,
    PROFILE_D_MLKEM1024,
)
from phoenix_sdr_dsp.pqc.dr30_3gpp_suci_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    suci_parse_validate_on_aie2,
    suci_decapsulate_derive_on_aie2,
    suci_deconceal_verify_on_aie2,
    suci_pipeline_full_on_aie2,
    ref_suci_validate_header,
    ref_derive_suci_keys,
    ref_compute_suci_mac,
    ref_decrypt_supi,
    ref_full_deconceal,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR30: 3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr30-3gpp-suci)")
    print("Standards: 3GPP TS 33.501, 3GPP TR 33.841 (Profile C & Profile D)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x30303030)

    # Preflight probe on hardware
    try:
        suci_parse_validate_on_aie2(PROFILE_C_MLKEM768, hn_key_id=1, suci_len=64, epoch=0)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr30-3gpp-suci:unavailable ({type(exc).__name__}: {exc})")
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

    # 1. Gate 1: 3GPP SUCI Header Parsing & Validation (6 cases)
    print("\n--- Gate 1: 3GPP SUCI Header Parsing & Validation (6 cases) ---")
    header_test_specs = [
        (PROFILE_C_MLKEM768,   1, 64,  "valid_profile_c"),
        (PROFILE_D_MLKEM1024,  2, 128, "valid_profile_d"),
        (PROFILE_NULL,         1, 64,  "invalid_profile_null"),
        (PROFILE_A_CURVE25519, 1, 64,  "non_pqc_profile_a"),
        (PROFILE_C_MLKEM768,   0, 64,  "invalid_hn_key_id_zero"),
        (PROFILE_C_MLKEM768,   1, 16,  "truncated_suci_len"),
    ]
    for i, (prof_id, key_id, s_len, label) in enumerate(header_test_specs):
        case_id = f"dr30_header_case_{i:03d}_{label}"
        exp_valid = ref_suci_validate_header(prof_id, key_id, s_len)

        t_start = time.perf_counter_ns()
        try:
            res_dict, dt_ms = suci_parse_validate_on_aie2(prof_id, key_id, s_len, epoch=100 + i)
            act_valid = res_dict["is_valid"]
            ok = (act_valid == exp_valid)
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
            "case_label": f"SUCI Header case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms:.2f}ms, valid={res_dict['is_valid']})")
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
                "details": "validation mismatch",
            })

    # 2. Gate 2: Shared Secret Decapsulation & KDF Expansion (6 cases)
    print("\n--- Gate 2: Shared Secret Decapsulation & KDF Expansion (6 cases) ---")
    for i in range(6):
        case_id = f"dr30_kdf_case_{i:03d}"
        ss = rng.bytes(32)
        ephem = rng.bytes(32)
        exp_keys = ref_derive_suci_keys(ss, ephem)

        t_start = time.perf_counter_ns()
        try:
            act_keys, dt_ms = suci_decapsulate_derive_on_aie2(ss, ephem, epoch=200 + i)
            act_k_enc = act_keys["k_enc"]
            act_k_mac = act_keys["k_mac"]
            exp_k_enc = exp_keys["k_enc"]
            exp_k_mac = exp_keys["k_mac"]
            ok = (act_k_enc == exp_k_enc) and (act_k_mac == exp_k_mac)
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
            "case_label": f"SUCI KDF case {i+1}",
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
                "details": "derived keys mismatch",
            })

    # 3. Gate 3: SUPI Decryption & MAC Verification (7 cases: 5 valid, 2 tampered MAC)
    print("\n--- Gate 3: SUPI Decryption & MAC Verification (7 cases) ---")
    for i in range(7):
        case_id = f"dr30_deconceal_case_{i:03d}"
        k_enc = rng.bytes(16)
        k_mac = rng.bytes(16)
        supi_plain = f"310260{rng.integers(1000000000, 9999999999)}".encode("ascii")[:16]
        enc_payload = ref_decrypt_supi(k_enc, supi_plain)
        valid_mac = ref_compute_suci_mac(k_mac, enc_payload)

        is_tampered = (i >= 5)
        recv_mac = bytearray(valid_mac)
        if is_tampered:
            recv_mac[0] ^= 0x55
            case_id += "_tampered_negative"

        t_start = time.perf_counter_ns()
        try:
            if not is_tampered:
                act_plain, dt_ms = suci_deconceal_verify_on_aie2(k_enc, k_mac, bytes(recv_mac), enc_payload, epoch=300 + i)
                ok = (act_plain == supi_plain)
            else:
                # Expect error status
                try:
                    act_plain, dt_ms = suci_deconceal_verify_on_aie2(k_enc, k_mac, bytes(recv_mac), enc_payload, epoch=300 + i)
                    ok = False
                except RuntimeError as rexc:
                    ok = ("0x02" in str(rexc))
                    dt_ms = 0.5
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
            "case_label": f"SUCI Deconceal case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            status_str = "REJECTED_AS_EXPECTED" if is_tampered else f"PASS ({dt_ms:.2f}ms)"
            print(f"  [{completed:02d}/25] {case_id:<45} {status_str}")
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
                "details": "deconceal mismatch",
            })

    # 4. Gate 4: End-to-End Atomic SUCI Pipeline (6 cases)
    print("\n--- Gate 4: End-to-End Atomic SUCI Pipeline (6 cases) ---")
    for i in range(6):
        case_id = f"dr30_full_pipeline_case_{i:03d}"
        ss = rng.bytes(32)
        ephem = rng.bytes(32)
        keys = ref_derive_suci_keys(ss, ephem)

        original_supi = f"IMSI310260{rng.integers(1000000000, 9999999999)}".encode("ascii")[:16]
        enc_payload = ref_decrypt_supi(keys["k_enc"], original_supi)
        mac = ref_compute_suci_mac(keys["k_mac"], enc_payload)

        t_start = time.perf_counter_ns()
        try:
            act_supi, dt_ms = suci_pipeline_full_on_aie2(ss, ephem, mac, enc_payload, epoch=400 + i)
            ok = (act_supi == original_supi)
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
            "case_label": f"SUCI Full Pipeline case {i+1}",
            "name": case_id,
        })
        if ok:
            passed += 1
            print(f"  [{completed:02d}/25] {case_id:<45} PASS ({dt_ms:.2f}ms, de-concealed={act_supi.decode('ascii', errors='ignore')})")
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
                "details": "full pipeline mismatch",
            })

    expected_total = 25
    exit_code = 0 if passed == expected_total else 1
    ended_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR30",
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
