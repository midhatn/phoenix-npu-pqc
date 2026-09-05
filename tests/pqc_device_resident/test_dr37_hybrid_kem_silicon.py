# SPDX-License-Identifier: Apache-2.0
"""Milestone DR37: Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Standards: ETSI TS 103 744, BSI TR-02102-1, IETF RFC 9180 (HPKE), NIST SP 800-56C Rev. 2.
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

from phoenix_sdr_dsp.pqc.dr37_hybrid_kem_abi import (
    MAGIC_HEADER,
    MAGIC_RESULT,
    MODE_HYBRID_ENCAPS_COMBINE,
    MODE_HYBRID_DECAPS_COMBINE,
    MODE_HYBRID_SPLIT_SECRET,
    MODE_HYBRID_POLICY_ENFORCE,
    MODE_HYBRID_ZEROIZE,
    PROFILE_X25519_MLKEM768,
    PROFILE_SECP384R1_MLKEM1024,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_DEGENERATE_KEY,
    STATUS_ERR_POLICY_VIOLATION,
    STATUS_ERR_INVALID_PROFILE,
    STATUS_ERR_INTEGRITY_FAIL,
    DESC_TOTAL_BYTES,
    REQ_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr37_descriptor,
    pack_dr37_request,
    unpack_dr37_result,
    reference_dr37_oracle,
)
from phoenix_sdr_dsp.pqc.dr37_hybrid_kem_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr37_hybrid_kem_on_aie2,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR37: Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr37-hybrid-kem)")
    print("Standards: ETSI TS 103 744, BSI TR-02102-1, RFC 9180, NIST SP 800-56C Rev. 2")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x37373737)

    # Preflight hardware probe
    try:
        dummy_c_ss = bytes([1] * 32)
        dummy_pqc_ss = bytes([2] * 32)
        run_dr37_hybrid_kem_on_aie2(
            op_mode=MODE_HYBRID_ZEROIZE,
            classical_ss=dummy_c_ss,
            pqc_ss=dummy_pqc_ss,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr37-hybrid-kem:unavailable ({type(exc).__name__}: {exc})")
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
    # Gate 1: X25519 + ML-KEM-768 Combiner (8 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 1: X25519 + ML-KEM-768 Combiner (8 cases) ---")
    gate1_cases = [
        ("fixed_identity", bytes([1] * 32), bytes([2] * 32), bytes([3] * 32), bytes([4] * 32), 1088, MODE_HYBRID_ENCAPS_COMBINE),
        ("fixed_reverse", bytes([0xAA] * 32), bytes([0x55] * 32), bytes([0x12] * 32), bytes([0x34] * 32), 1088, MODE_HYBRID_ENCAPS_COMBINE),
        ("decaps_profile1_a", bytes([0x22] * 32), bytes([0x33] * 32), bytes([0x44] * 32), bytes([0x55] * 32), 1088, MODE_HYBRID_DECAPS_COMBINE),
        ("decaps_profile1_b", bytes([0x66] * 32), bytes([0x77] * 32), bytes([0x88] * 32), bytes([0x99] * 32), 1088, MODE_HYBRID_DECAPS_COMBINE),
        ("random_encaps_0", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1088, MODE_HYBRID_ENCAPS_COMBINE),
        ("random_encaps_1", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1088, MODE_HYBRID_ENCAPS_COMBINE),
        ("random_decaps_0", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1088, MODE_HYBRID_DECAPS_COMBINE),
        ("random_decaps_1", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1088, MODE_HYBRID_DECAPS_COMBINE),
    ]

    for name, c_ss, pqc_ss, c_ct, salt, pqc_ct_len, mode in gate1_cases:
        cid = f"dr37-gate1-x25519-mlkem768-{name}"
        seq = completed + 1
        pqc_ct = bytes(rng.integers(0, 256, size=pqc_ct_len, dtype=np.uint8))

        desc = pack_dr37_descriptor(
            op_mode=mode,
            profile_id=PROFILE_X25519_MLKEM768,
            ct_pqc_len=pqc_ct_len,
            seq_id=seq,
        )
        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )
        exp_res = reference_dr37_oracle(req, desc)

        act_res, dt_ms = run_dr37_hybrid_kem_on_aie2(
            op_mode=mode,
            profile_id=PROFILE_X25519_MLKEM768,
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
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
            "expected_hex": exp_res[:160].hex(),
            "actual_hex": act_res[:160].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    # -------------------------------------------------------------------------
    # Gate 2: SecP384R1 + ML-KEM-1024 Combiner (8 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 2: SecP384R1 + ML-KEM-1024 Combiner (8 cases) ---")
    gate2_cases = [
        ("fixed_identity", bytes([5] * 32), bytes([6] * 32), bytes([7] * 32), bytes([8] * 32), 1568, MODE_HYBRID_ENCAPS_COMBINE),
        ("fixed_pattern", bytes([0xCC] * 32), bytes([0x33] * 32), bytes([0x77] * 32), bytes([0x88] * 32), 1568, MODE_HYBRID_ENCAPS_COMBINE),
        ("decaps_profile2_a", bytes([0x44] * 32), bytes([0x55] * 32), bytes([0x66] * 32), bytes([0x77] * 32), 1568, MODE_HYBRID_DECAPS_COMBINE),
        ("decaps_profile2_b", bytes([0x88] * 32), bytes([0x99] * 32), bytes([0xAA] * 32), bytes([0xBB] * 32), 1568, MODE_HYBRID_DECAPS_COMBINE),
        ("random_encaps_0", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1568, MODE_HYBRID_ENCAPS_COMBINE),
        ("random_encaps_1", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1568, MODE_HYBRID_ENCAPS_COMBINE),
        ("random_decaps_0", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1568, MODE_HYBRID_DECAPS_COMBINE),
        ("random_decaps_1", bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(1, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), 1568, MODE_HYBRID_DECAPS_COMBINE),
    ]

    for name, c_ss, pqc_ss, c_ct, salt, pqc_ct_len, mode in gate2_cases:
        cid = f"dr37-gate2-secp384r1-mlkem1024-{name}"
        seq = completed + 1
        pqc_ct = bytes(rng.integers(0, 256, size=pqc_ct_len, dtype=np.uint8))

        desc = pack_dr37_descriptor(
            op_mode=mode,
            profile_id=PROFILE_SECP384R1_MLKEM1024,
            ct_pqc_len=pqc_ct_len,
            seq_id=seq,
        )
        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )
        exp_res = reference_dr37_oracle(req, desc)

        act_res, dt_ms = run_dr37_hybrid_kem_on_aie2(
            op_mode=mode,
            profile_id=PROFILE_SECP384R1_MLKEM1024,
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
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
            "expected_hex": exp_res[:160].hex(),
            "actual_hex": act_res[:160].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    # -------------------------------------------------------------------------
    # Gate 3: Transcript Binding & HKDF Key Expansion Invariance (5 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 3: Transcript Binding & HKDF Invariance (5 cases) ---")
    gate3_cases = [
        ("empty_salt", bytes([9] * 32), bytes([10] * 32), bytes([11] * 32), bytes(32), 1088),
        ("varying_salt_1", bytes([9] * 32), bytes([10] * 32), bytes([11] * 32), bytes([0xFE] * 32), 1088),
        ("varying_salt_2", bytes([9] * 32), bytes([10] * 32), bytes([11] * 32), bytes([0xEF] * 32), 1088),
        ("transcript_sensitivity_a", bytes([12] * 32), bytes([13] * 32), bytes([0x01] * 32), bytes([0x02] * 32), 1088),
        ("transcript_sensitivity_b", bytes([12] * 32), bytes([13] * 32), bytes([0x02] * 32), bytes([0x02] * 32), 1088),
    ]

    for name, c_ss, pqc_ss, c_ct, salt, pqc_ct_len in gate3_cases:
        cid = f"dr37-gate3-transcript-hkdf-{name}"
        seq = completed + 1
        pqc_ct = bytes(rng.integers(0, 256, size=pqc_ct_len, dtype=np.uint8))

        desc = pack_dr37_descriptor(
            op_mode=MODE_HYBRID_ENCAPS_COMBINE,
            profile_id=PROFILE_X25519_MLKEM768,
            ct_pqc_len=pqc_ct_len,
            seq_id=seq,
        )
        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )
        exp_res = reference_dr37_oracle(req, desc)

        act_res, dt_ms = run_dr37_hybrid_kem_on_aie2(
            op_mode=MODE_HYBRID_ENCAPS_COMBINE,
            profile_id=PROFILE_X25519_MLKEM768,
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
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
            "expected_hex": exp_res[:160].hex(),
            "actual_hex": act_res[:160].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    # -------------------------------------------------------------------------
    # Gate 4: Security Policy & Degenerate Key Protection (4 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 4: Security Policy & Degenerate Key Protection (4 cases) ---")
    gate4_cases = [
        ("degenerate_classical_zero", bytes(32), bytes([0x22] * 32), MODE_HYBRID_POLICY_ENFORCE, PROFILE_X25519_MLKEM768),
        ("degenerate_pqc_zero", bytes([0x11] * 32), bytes(32), MODE_HYBRID_POLICY_ENFORCE, PROFILE_X25519_MLKEM768),
        ("zeroize_profile1", bytes([0xAA] * 32), bytes([0xBB] * 32), MODE_HYBRID_ZEROIZE, PROFILE_X25519_MLKEM768),
        ("zeroize_profile2", bytes([0xCC] * 32), bytes([0xDD] * 32), MODE_HYBRID_ZEROIZE, PROFILE_SECP384R1_MLKEM1024),
    ]

    for name, c_ss, pqc_ss, mode, prof in gate4_cases:
        cid = f"dr37-gate4-policy-{name}"
        seq = completed + 1
        c_ct = bytes([0x33] * 32)
        salt = bytes([0x44] * 32)
        pqc_ct = bytes([0x55] * 1088)

        desc = pack_dr37_descriptor(
            op_mode=mode,
            profile_id=prof,
            ct_pqc_len=1088,
            seq_id=seq,
        )
        req = pack_dr37_request(
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
        )
        exp_res = reference_dr37_oracle(req, desc)

        act_res, dt_ms = run_dr37_hybrid_kem_on_aie2(
            op_mode=mode,
            profile_id=prof,
            classical_ss=c_ss,
            pqc_ss=pqc_ss,
            classical_ct=c_ct,
            salt=salt,
            pqc_ct=pqc_ct,
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
            "expected_hex": exp_res[:160].hex(),
            "actual_hex": act_res[:160].hex(),
        })
        print(f"  {cid}: {'PASS' if match else 'FAIL'} ({dt_ms:.2f} ms)")

    completed_at = datetime.now(timezone.utc).isoformat()
    success = (completed == 25 and passed == 25)

    result_payload = {
        "deliverable": "DR37",
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

    print(f"\nDR37 Final Result: {passed}/{completed} cases passed ({'SUCCESS' if success else 'FAILURE'})")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
