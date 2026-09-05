# SPDX-License-Identifier: Apache-2.0
"""Milestone DR41: Quantum Key Management System (Q-KMS) Integration & Key Lifecycle Engine Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Standards: ETSI GS QKD 014/015, OASIS KMIP v2.1, NIST SP 800-57 Part 1 Rev. 5, NIST SP 800-56C Rev. 2.
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

from phoenix_sdr_dsp.pqc.dr41_qkms_abi import (
    MAGIC_HEADER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_INVALID_SLOT,
    STATUS_ERR_ILLEGAL_TRANSITION,
    STATUS_ERR_SLOT_EXPIRED,
    STATUS_ERR_UNSUPPORTED_OP,
    STATUS_ERR_KEY_COMPROMISED,
    OP_VAULT_STORE,
    OP_VAULT_DERIVE,
    OP_VAULT_TRANSITION,
    OP_VAULT_ZEROIZE,
    OP_VAULT_QUERY,
    STATE_EMPTY,
    STATE_PRE_ACTIVE,
    STATE_ACTIVE,
    STATE_DEACTIVATED,
    STATE_COMPROMISED,
    STATE_DESTROYED,
    KEY_TYPE_QKD,
    KEY_TYPE_PQC_SHARED_SECRET,
    KEY_TYPE_DERIVED_SESSION,
    DESCRIPTOR_SIZE,
    REQUEST_BUFFER_SIZE,
    RESULT_BUFFER_SIZE,
    NUM_VAULT_SLOTS,
    QkmsDescriptor,
    QkmsResultHeader,
    VaultSlot,
    pack_vault_bank,
    unpack_vault_bank,
    build_request_tensor,
    compute_reference_oracle,
)
from phoenix_sdr_dsp.pqc.dr41_qkms_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr41_qkms_on_aie2,
    NativeBackendUnavailable,
    _dispatch_dr41,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR41: Quantum Key Management System (Q-KMS) & Lifecycle Silicon Suite")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr41-qkms-lifecycle)")
    print("Standards: ETSI GS QKD 014/015, OASIS KMIP, NIST SP 800-57, SP 800-56C")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x41414141)

    # Preflight hardware probe
    try:
        run_dr41_qkms_on_aie2(
            op_code=OP_VAULT_QUERY,
            slot_id=0,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr41-qkms-lifecycle:unavailable ({type(exc).__name__}: {exc})")
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

    # Maintain local tracking vault across test flow
    active_vault = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]

    # -------------------------------------------------------------------------
    # Gate 1: Secure Ingress & Vault Slot Allocation (7 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 1: Secure Ingress & Vault Slot Allocation (7 cases) ---")
    gate1_configs = [
        (0, STATE_ACTIVE, KEY_TYPE_QKD, 1, b"QKD_OPTICAL_KEY0", b"\x11" * 32, "slot-0-qkd-active"),
        (1, STATE_ACTIVE, KEY_TYPE_PQC_SHARED_SECRET, 1, b"PQC_SECRET_KEY01", b"\x22" * 32, "slot-1-pqc-active"),
        (2, STATE_PRE_ACTIVE, KEY_TYPE_QKD, 1, b"PREACT_QKD_SLOT2", b"\x33" * 32, "slot-2-preactive"),
        (3, STATE_ACTIVE, KEY_TYPE_DERIVED_SESSION, 2, b"SESS_KEY_SLOT_03", b"\x44" * 32, "slot-3-session"),
        (4, STATE_ACTIVE, KEY_TYPE_QKD, 3, b"QKD_KEY_SLOT_004", b"\x55" * 32, "slot-4-qkd-custom"),
        (5, STATE_ACTIVE, KEY_TYPE_PQC_SHARED_SECRET, 10, b"PQC_EPOCH10_SL05", b"\x66" * 32, "slot-5-pqc-epoch10"),
        (6, STATE_PRE_ACTIVE, KEY_TYPE_QKD, 1, b"BACKUP_KEY_SLT06", b"\x77" * 32, "slot-6-backup-preactive"),
    ]

    for slot, state, ktype, ep, kid, kmat, name in gate1_configs:
        cid = f"dr41-gate1-ingress-{name}"
        seq = completed + 1

        payload = kmat + kid
        req = build_request_tensor(payload=payload, vault=active_vault)

        exp_oracle, active_vault = compute_reference_oracle(
            op_code=OP_VAULT_STORE,
            slot_id=slot,
            request_bytes=req,
            target_state=state,
            key_type=ktype,
            epoch=ep,
            initial_vault=active_vault,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr41_qkms_on_aie2(
            op_code=OP_VAULT_STORE,
            slot_id=slot,
            target_state=state,
            key_type=ktype,
            epoch=ep,
            seq_id=seq,
            raw_request_buffer=req,
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
    # Gate 2: NIST SP 800-56C Dual KDF Session Derivation (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 2: NIST SP 800-56C Dual KDF Session Derivation (6 cases) ---")
    gate2_configs = [
        (0, 1, 7, bytes((i * 7 + 3) % 256 for i in range(32)), 2, "derive-slot0-slot1-to-slot7-salt-alpha"),
        (0, 1, 7, bytes((i * 13 + 5) % 256 for i in range(32)), 3, "derive-slot0-slot1-to-slot7-salt-beta"),
        (3, 4, 2, bytes(32), 4, "derive-slot3-slot4-to-slot2-zero-salt"),
        (4, 5, 3, bytes((i * 17 + 1) % 256 for i in range(32)), 5, "derive-slot4-slot5-to-slot3-counter-salt"),
    ]

    for s0, s1, target_slot, salt, ep, name in gate2_configs:
        cid = f"dr41-gate2-kdf-{name}"
        seq = completed + 1

        req = build_request_tensor(payload=salt, vault=active_vault)
        exp_oracle, active_vault = compute_reference_oracle(
            op_code=OP_VAULT_DERIVE,
            slot_id=target_slot,
            request_bytes=req,
            param_0=s0,
            param_1=s1,
            epoch=ep,
            initial_vault=active_vault,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr41_qkms_on_aie2(
            op_code=OP_VAULT_DERIVE,
            slot_id=target_slot,
            param_0=s0,
            param_1=s1,
            epoch=ep,
            seq_id=seq,
            raw_request_buffer=req,
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

    # Gate 2 Queries:
    for qslot, name in [(7, "query-derived-slot7"), (2, "query-derived-slot2")]:
        cid = f"dr41-gate2-query-{name}"
        seq = completed + 1

        req = build_request_tensor(vault=active_vault)
        exp_oracle, _ = compute_reference_oracle(
            op_code=OP_VAULT_QUERY,
            slot_id=qslot,
            request_bytes=req,
            initial_vault=active_vault,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr41_qkms_on_aie2(
            op_code=OP_VAULT_QUERY,
            slot_id=qslot,
            seq_id=seq,
            raw_request_buffer=req,
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
    # Gate 3: NIST SP 800-57 / KMIP Lifecycle State Transitions (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 3: NIST SP 800-57 / KMIP Lifecycle State Transitions (6 cases) ---")
    gate3_transitions = [
        (6, STATE_ACTIVE, "transition-slot6-preactive-to-active"),
        (0, STATE_DEACTIVATED, "transition-slot0-active-to-deactivated"),
        (1, STATE_COMPROMISED, "transition-slot1-active-to-compromised"),
        (0, STATE_DESTROYED, "transition-slot0-deactivated-to-destroyed"),
        (1, STATE_DESTROYED, "transition-slot1-compromised-to-destroyed"),
        (6, STATE_DESTROYED, "transition-slot6-active-to-destroyed"),
    ]

    for slot, target_state, name in gate3_transitions:
        cid = f"dr41-gate3-{name}"
        seq = completed + 1

        req = build_request_tensor(vault=active_vault)
        exp_oracle, active_vault = compute_reference_oracle(
            op_code=OP_VAULT_TRANSITION,
            slot_id=slot,
            request_bytes=req,
            target_state=target_state,
            initial_vault=active_vault,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr41_qkms_on_aie2(
            op_code=OP_VAULT_TRANSITION,
            slot_id=slot,
            target_state=target_state,
            seq_id=seq,
            raw_request_buffer=req,
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
    # Gate 4: Zeroization, Boundary Robustness & Error Rejection (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 4: Zeroization, Boundary Robustness & Error Rejection (6 cases) ---")

    # Case 20: Single Slot Zeroization (Slot 4)
    cid20 = "dr41-gate4-zeroize-slot4"
    seq = completed + 1
    req20 = build_request_tensor(vault=active_vault)
    exp_o20, active_vault = compute_reference_oracle(OP_VAULT_ZEROIZE, 4, req20, initial_vault=active_vault)
    exp_res20 = exp_o20.pack()
    act_res20, dt20 = run_dr41_qkms_on_aie2(OP_VAULT_ZEROIZE, 4, seq_id=seq, raw_request_buffer=req20)
    m20 = (act_res20 == exp_res20)
    completed += 1; passed += int(m20)
    case_results.append({"case_id": cid20, "status": "PASS" if m20 else "FAIL", "runtime_ms": round(dt20, 3)})
    test_buffers.append({"case_id": cid20, "expected_hex": exp_res20[:64].hex(), "actual_hex": act_res20[:64].hex()})
    print(f"  {cid20}: {'PASS' if m20 else 'FAIL'} ({dt20:.2f} ms)")

    # Case 21: Full Vault Zeroization (0xFF)
    cid21 = "dr41-gate4-zeroize-all-slots"
    seq = completed + 1
    req21 = build_request_tensor(vault=active_vault)
    exp_o21, active_vault = compute_reference_oracle(OP_VAULT_ZEROIZE, 0xFF, req21, initial_vault=active_vault)
    exp_res21 = exp_o21.pack()
    act_res21, dt21 = run_dr41_qkms_on_aie2(OP_VAULT_ZEROIZE, 0xFF, seq_id=seq, raw_request_buffer=req21)
    m21 = (act_res21 == exp_res21)
    completed += 1; passed += int(m21)
    case_results.append({"case_id": cid21, "status": "PASS" if m21 else "FAIL", "runtime_ms": round(dt21, 3)})
    test_buffers.append({"case_id": cid21, "expected_hex": exp_res21[:64].hex(), "actual_hex": act_res21[:64].hex()})
    print(f"  {cid21}: {'PASS' if m21 else 'FAIL'} ({dt21:.2f} ms)")

    # Case 22: Boundary - Illegal Transition Rejection (DESTROYED -> ACTIVE)
    cid22 = "dr41-gate4-boundary-illegal-transition"
    seq = completed + 1
    req22 = build_request_tensor(vault=active_vault)
    exp_o22, active_vault = compute_reference_oracle(OP_VAULT_TRANSITION, 0, req22, target_state=STATE_ACTIVE, initial_vault=active_vault)
    exp_res22 = exp_o22.pack()
    act_res22, dt22 = run_dr41_qkms_on_aie2(OP_VAULT_TRANSITION, 0, target_state=STATE_ACTIVE, seq_id=seq, raw_request_buffer=req22)
    m22 = (act_res22 == exp_res22)
    completed += 1; passed += int(m22)
    case_results.append({"case_id": cid22, "status": "PASS" if m22 else "FAIL", "runtime_ms": round(dt22, 3)})
    test_buffers.append({"case_id": cid22, "expected_hex": exp_res22[:64].hex(), "actual_hex": act_res22[:64].hex()})
    print(f"  {cid22}: {'PASS' if m22 else 'FAIL'} ({dt22:.2f} ms)")

    # Case 23: Boundary - Invalid Magic Header Rejection
    cid23 = "dr41-gate4-boundary-invalid-magic"
    bad_magic_desc = QkmsDescriptor(
        op_code=OP_VAULT_QUERY,
        slot_id=0,
        magic=0xDEADBEEF,
    ).pack()
    act_bad_magic, dt23 = _dispatch_dr41(bad_magic_desc, bytes(REQUEST_BUFFER_SIZE))
    hdr23 = QkmsResultHeader.unpack(act_bad_magic)
    m23 = (hdr23.status == STATUS_ERR_INVALID_MAGIC)
    completed += 1; passed += int(m23)
    case_results.append({"case_id": cid23, "status": "PASS" if m23 else "FAIL", "runtime_ms": round(dt23, 3)})
    test_buffers.append({"case_id": cid23, "expected_hex": hex(STATUS_ERR_INVALID_MAGIC), "actual_hex": hex(hdr23.status)})
    print(f"  {cid23}: {'PASS' if m23 else 'FAIL'} (status={hex(hdr23.status)})")

    # Case 24: Boundary - Invalid Slot ID Rejection (slot_id=99)
    cid24 = "dr41-gate4-boundary-invalid-slot"
    seq = completed + 1
    bad_slot_desc = QkmsDescriptor(
        op_code=OP_VAULT_QUERY,
        slot_id=99,
    ).pack()
    act_bad_slot, dt24 = _dispatch_dr41(bad_slot_desc, bytes(REQUEST_BUFFER_SIZE))
    hdr24 = QkmsResultHeader.unpack(act_bad_slot)
    m24 = (hdr24.status == STATUS_ERR_INVALID_SLOT)
    completed += 1; passed += int(m24)
    case_results.append({"case_id": cid24, "status": "PASS" if m24 else "FAIL", "runtime_ms": round(dt24, 3)})
    test_buffers.append({"case_id": cid24, "expected_hex": hex(STATUS_ERR_INVALID_SLOT), "actual_hex": hex(hdr24.status)})
    print(f"  {cid24}: {'PASS' if m24 else 'FAIL'} (status={hex(hdr24.status)})")

    # Case 25: Boundary - Compromised Key Derivation Rejection
    cid25 = "dr41-gate4-boundary-compromised-derivation"
    seq = completed + 1
    compromised_vault = [VaultSlot() for _ in range(NUM_VAULT_SLOTS)]
    compromised_vault[0] = VaultSlot(state=STATE_COMPROMISED, key_type=KEY_TYPE_QKD, key_material=b"\x11" * 32)
    compromised_vault[1] = VaultSlot(state=STATE_ACTIVE, key_type=KEY_TYPE_PQC_SHARED_SECRET, key_material=b"\x22" * 32)
    req25 = build_request_tensor(payload=bytes(32), vault=compromised_vault)
    exp_o25, _ = compute_reference_oracle(
        op_code=OP_VAULT_DERIVE,
        slot_id=2,
        request_bytes=req25,
        param_0=0,
        param_1=1,
        initial_vault=compromised_vault,
    )
    exp_res25 = exp_o25.pack()
    act_res25, dt25 = run_dr41_qkms_on_aie2(
        op_code=OP_VAULT_DERIVE,
        slot_id=2,
        param_0=0,
        param_1=1,
        seq_id=seq,
        raw_request_buffer=req25,
    )
    m25 = (act_res25 == exp_res25)
    completed += 1; passed += int(m25)
    case_results.append({"case_id": cid25, "status": "PASS" if m25 else "FAIL", "runtime_ms": round(dt25, 3)})
    test_buffers.append({"case_id": cid25, "expected_hex": exp_res25[:64].hex(), "actual_hex": act_res25[:64].hex()})
    print(f"  {cid25}: {'PASS' if m25 else 'FAIL'} ({dt25:.2f} ms)")

    completed_at = datetime.now(timezone.utc).isoformat()
    success = (completed == 25 and passed == 25)

    result_payload = {
        "deliverable": "DR41",
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

    print(f"\nDR41 Final Result: {passed}/{completed} cases passed ({'SUCCESS' if success else 'FAILURE'})")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
