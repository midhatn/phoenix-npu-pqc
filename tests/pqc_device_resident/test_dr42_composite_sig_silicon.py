# SPDX-License-Identifier: Apache-2.0
"""Milestone DR42: ANSSI Composite & Dual-Signature Sovereign Standard Engine Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Standards: ANSSI 2022 Post-Quantum Transition, BSI TR-02102-1, IETF LAMPS Composite Signatures (draft-ietf-lamps-pq-composite-sigs-02).
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

from phoenix_sdr_dsp.pqc.dr42_composite_sig_abi import (
    MAGIC_HEADER,
    STATUS_SUCCESS,
    STATUS_ERR_INVALID_MAGIC,
    STATUS_ERR_UNSUPPORTED_TYPE,
    STATUS_ERR_TRAD_VERIFY_FAILED,
    STATUS_ERR_PQC_VERIFY_FAILED,
    STATUS_ERR_COMPOSITE_VERIFY_FAILED,
    STATUS_ERR_MALFORMED_SIGNATURE,
    STATUS_ERR_MALFORMED_KEY,
    STATUS_ERR_UNSUPPORTED_OP,
    OP_COMPOSITE_KEY_INGRESS,
    OP_COMPOSITE_DIGEST_BIND,
    OP_COMPOSITE_VERIFY,
    OP_COMPOSITE_PACK_SIGNATURE,
    OP_COMPOSITE_QUERY,
    COMPOSITE_TYPE_MLDSA44_ED25519,
    COMPOSITE_TYPE_MLDSA65_ECDSA_P384,
    COMPOSITE_TYPE_MLDSA87_ECDSA_P521,
    DESCRIPTOR_SIZE,
    REQUEST_BUFFER_SIZE,
    RESULT_BUFFER_SIZE,
    CompositeSigDescriptor,
    CompositeSigResultHeader,
    build_composite_request_tensor,
    compute_ietf_bound_digest_ref,
    compute_composite_fingerprint_ref,
    compute_reference_oracle,
)
from phoenix_sdr_dsp.pqc.dr42_composite_sig_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr42_composite_sig_on_aie2,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def _generate_key_and_sig_pair(sig_type: int, digest: bytes, seed: int = 1):
    rng = np.random.default_rng(seed=seed)
    if sig_type == COMPOSITE_TYPE_MLDSA44_ED25519:
        tpk_len, tsig_len = 32, 64
        ppk_len, psig_len = 1312, 2420
    elif sig_type == COMPOSITE_TYPE_MLDSA65_ECDSA_P384:
        tpk_len, tsig_len = 48, 96
        ppk_len, psig_len = 1952, 3309
    else:
        tpk_len, tsig_len = 66, 132
        ppk_len, psig_len = 2592, 4627

    trad_pk = bytearray(rng.integers(1, 255, size=tpk_len, dtype=np.uint8).tobytes())
    trad_sig = bytearray(rng.integers(1, 255, size=tsig_len, dtype=np.uint8).tobytes())
    pqc_pk = bytearray(rng.integers(1, 255, size=ppk_len, dtype=np.uint8).tobytes())
    pqc_sig = bytearray(rng.integers(1, 255, size=psig_len, dtype=np.uint8).tobytes())

    # Adjust classical parity zero
    chk_t = 0
    for i in range(min(32, tsig_len)):
        chk_t ^= (trad_sig[i] ^ trad_pk[i % tpk_len] ^ digest[i % len(digest)])
    if (chk_t & 0x01) != 0:
        trad_sig[0] ^= 0x01

    # Adjust PQC parity zero
    sig_tag = 0
    for i in range(min(32, psig_len)):
        sig_tag ^= pqc_sig[i] << ((i % 4) * 8)
    exp_tag = 0
    for i in range(min(32, len(digest))):
        exp_tag ^= digest[i] << ((i % 4) * 8)
    for i in range(min(32, ppk_len)):
        exp_tag ^= pqc_pk[i] << (((i + 1) % 4) * 8)
    if ((sig_tag ^ exp_tag) & 0x01) != 0:
        pqc_sig[0] ^= 0x01

    return bytes(trad_pk), bytes(trad_sig), bytes(pqc_pk), bytes(pqc_sig)


def main() -> int:
    print("=" * 75)
    print("DR42: ANSSI Composite & Dual-Signature Sovereign Standard Silicon Suite")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr42-composite-sig)")
    print("Standards: ANSSI 2022, BSI TR-02102-1, IETF LAMPS (draft-ietf-lamps-pq-composite-sigs-02)")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()

    # Preflight hardware probe
    try:
        run_dr42_composite_sig_on_aie2(
            op_code=OP_COMPOSITE_QUERY,
            sig_type=COMPOSITE_TYPE_MLDSA44_ED25519,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr42-composite-sig:unavailable ({type(exc).__name__}: {exc})")
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
    # Gate 1: Compound Key Ingress & Fingerprinting (7 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 1: Compound Key Ingress & Fingerprinting (7 cases) ---")
    gate1_configs = [
        (COMPOSITE_TYPE_MLDSA44_ED25519, 32, 1312, 101, "mldsa44-ed25519-primary"),
        (COMPOSITE_TYPE_MLDSA44_ED25519, 32, 1312, 102, "mldsa44-ed25519-secondary"),
        (COMPOSITE_TYPE_MLDSA65_ECDSA_P384, 48, 1952, 201, "mldsa65-p384-standard"),
        (COMPOSITE_TYPE_MLDSA65_ECDSA_P384, 48, 1952, 202, "mldsa65-p384-highsec"),
        (COMPOSITE_TYPE_MLDSA87_ECDSA_P521, 66, 2592, 301, "mldsa87-p521-sovereign"),
        (COMPOSITE_TYPE_MLDSA87_ECDSA_P521, 66, 2592, 302, "mldsa87-p521-cat5"),
        (COMPOSITE_TYPE_MLDSA44_ED25519, 32, 1312, 103, "mldsa44-ed25519-roundtrip"),
    ]

    for stype, tpk_len, ppk_len, seed, name in gate1_configs:
        cid = f"dr42-gate1-ingress-{name}"
        seq = completed + 1
        rng = np.random.default_rng(seed=seed)
        trad_pk = rng.integers(1, 255, size=tpk_len, dtype=np.uint8).tobytes()
        pqc_pk = rng.integers(1, 255, size=ppk_len, dtype=np.uint8).tobytes()

        req = build_composite_request_tensor(trad_pk=trad_pk, pqc_pk=pqc_pk)
        exp_oracle = compute_reference_oracle(
            op_code=OP_COMPOSITE_KEY_INGRESS,
            sig_type=stype,
            request_bytes=req,
            trad_pk_len=tpk_len,
            pqc_pk_len=ppk_len,
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr42_composite_sig_on_aie2(
            op_code=OP_COMPOSITE_KEY_INGRESS,
            sig_type=stype,
            trad_pk_len=tpk_len,
            pqc_pk_len=ppk_len,
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
    # Gate 2: IETF Domain-Separated Digest Binding (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 2: IETF Domain-Separated Digest Binding (6 cases) ---")
    gate2_configs = [
        (COMPOSITE_TYPE_MLDSA44_ED25519, b"OID_CAT2_NO_CTX".ljust(32, b"\x00"), b"", b"MSG_PAYLOAD_01", "mldsa44-no-ctx"),
        (COMPOSITE_TYPE_MLDSA44_ED25519, b"OID_CAT2_ANSSI".ljust(32, b"\x00"), b"ANSSI_TRANSITION", b"MSG_ANSSI_SOVEREIGN", "mldsa44-anssi-ctx"),
        (COMPOSITE_TYPE_MLDSA65_ECDSA_P384, b"OID_CAT3_BSI".ljust(32, b"\x00"), b"BSI_TR02102_CTX", b"MSG_BSI_RECOMMENDATION", "mldsa65-bsi-ctx"),
        (COMPOSITE_TYPE_MLDSA65_ECDSA_P384, b"OID_CAT3_IETF".ljust(32, b"\x00"), b"IETF_LAMPS_PREHASH", b"MSG_INTERNET_PKI_CERT", "mldsa65-ietf-ctx"),
        (COMPOSITE_TYPE_MLDSA87_ECDSA_P521, b"OID_CAT5_SOV".ljust(32, b"\x00"), b"SOVEREIGN_ROOT_CA", b"CRITICAL_INFRASTRUCTURE", "mldsa87-sovereign-ctx"),
        (COMPOSITE_TYPE_MLDSA87_ECDSA_P521, b"OID_CAT5_LONG".ljust(32, b"\x00"), b"EXTENDED_CONTEXT", bytes(range(128)), "mldsa87-long-msg"),
    ]

    for stype, oid, ctx, msg, name in gate2_configs:
        cid = f"dr42-gate2-digest-{name}"
        seq = completed + 1

        req = build_composite_request_tensor(oid=oid, context=ctx, message=msg)
        exp_oracle = compute_reference_oracle(
            op_code=OP_COMPOSITE_DIGEST_BIND,
            sig_type=stype,
            request_bytes=req,
            msg_len=len(msg),
            context_len=len(ctx),
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr42_composite_sig_on_aie2(
            op_code=OP_COMPOSITE_DIGEST_BIND,
            sig_type=stype,
            msg_len=len(msg),
            context_len=len(ctx),
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
    # Gate 3: Atomic Dual-Signature Verification Conjunction (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 3: Atomic Dual-Signature Verification Conjunction (6 cases) ---")
    gate3_configs = [
        (COMPOSITE_TYPE_MLDSA44_ED25519, b"OID_CAT2_V1".ljust(32, b"\x00"), b"CTX1", b"VERIFY_VALID_CAT2", True, True, "mldsa44-ed25519-both-valid"),
        (COMPOSITE_TYPE_MLDSA65_ECDSA_P384, b"OID_CAT3_V1".ljust(32, b"\x00"), b"CTX2", b"VERIFY_VALID_CAT3", True, True, "mldsa65-p384-both-valid"),
        (COMPOSITE_TYPE_MLDSA87_ECDSA_P521, b"OID_CAT5_V1".ljust(32, b"\x00"), b"CTX3", b"VERIFY_VALID_CAT5", True, True, "mldsa87-p521-both-valid"),
        (COMPOSITE_TYPE_MLDSA44_ED25519, b"OID_CAT2_V2".ljust(32, b"\x00"), b"CTX1", b"VERIFY_TRAD_FAIL", False, True, "mldsa44-ed25519-trad-fail-closed"),
        (COMPOSITE_TYPE_MLDSA65_ECDSA_P384, b"OID_CAT3_V2".ljust(32, b"\x00"), b"CTX2", b"VERIFY_PQC_FAIL", True, False, "mldsa65-p384-pqc-fail-closed"),
        (COMPOSITE_TYPE_MLDSA87_ECDSA_P521, b"OID_CAT5_V2".ljust(32, b"\x00"), b"CTX3", b"VERIFY_BOTH_FAIL", False, False, "mldsa87-p521-both-failed"),
    ]

    for stype, oid, ctx, msg, trad_valid, pqc_valid, name in gate3_configs:
        cid = f"dr42-gate3-verify-{name}"
        seq = completed + 1

        d = compute_ietf_bound_digest_ref(oid, ctx, msg)
        tpk, tsig, ppk, psig = _generate_key_and_sig_pair(stype, d, seed=seq * 7)

        if not trad_valid:
            tsig_mut = bytearray(tsig)
            tsig_mut[0] ^= 0x01
            tsig = bytes(tsig_mut)
        if not pqc_valid:
            psig_mut = bytearray(psig)
            psig_mut[0] ^= 0x01
            psig = bytes(psig_mut)

        req = build_composite_request_tensor(
            oid=oid,
            context=ctx,
            message=msg,
            trad_pk=tpk,
            trad_sig=tsig,
            pqc_pk=ppk,
            pqc_sig=psig,
        )

        exp_oracle = compute_reference_oracle(
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=stype,
            request_bytes=req,
            msg_len=len(msg),
            context_len=len(ctx),
            trad_pk_len=len(tpk),
            trad_sig_len=len(tsig),
            pqc_pk_len=len(ppk),
            pqc_sig_len=len(psig),
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr42_composite_sig_on_aie2(
            op_code=OP_COMPOSITE_VERIFY,
            sig_type=stype,
            msg_len=len(msg),
            context_len=len(ctx),
            trad_pk_len=len(tpk),
            trad_sig_len=len(tsig),
            pqc_pk_len=len(ppk),
            pqc_sig_len=len(psig),
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
    # Gate 4: Boundary Robustness, Tamper Detection & Malformed Rejection (6 cases)
    # -------------------------------------------------------------------------
    print("\n--- Gate 4: Boundary Robustness, Tamper Detection & Malformed Rejection (6 cases) ---")
    gate4_configs = [
        ("pack-sig-mldsa44", OP_COMPOSITE_PACK_SIGNATURE, COMPOSITE_TYPE_MLDSA44_ED25519, b"\x11" * 64, b"\x22" * 2420, b"", b""),
        ("pack-sig-mldsa65", OP_COMPOSITE_PACK_SIGNATURE, COMPOSITE_TYPE_MLDSA65_ECDSA_P384, b"\x33" * 96, b"\x44" * 3309, b"", b""),
        ("pack-sig-zero-rejected", OP_COMPOSITE_PACK_SIGNATURE, COMPOSITE_TYPE_MLDSA44_ED25519, bytes(64), b"\x22" * 2420, b"", b""),
        ("ingress-zero-pk-rejected", OP_COMPOSITE_KEY_INGRESS, COMPOSITE_TYPE_MLDSA44_ED25519, b"", b"", bytes(32), b"\x44" * 1312),
        ("query-cat3", OP_COMPOSITE_QUERY, COMPOSITE_TYPE_MLDSA65_ECDSA_P384, b"", b"", b"", b""),
        ("query-cat5", OP_COMPOSITE_QUERY, COMPOSITE_TYPE_MLDSA87_ECDSA_P521, b"", b"", b"", b""),
    ]

    for name, opcode, stype, tsig, psig, tpk, ppk in gate4_configs:
        cid = f"dr42-gate4-boundary-{name}"
        seq = completed + 1

        req = build_composite_request_tensor(
            trad_sig=tsig,
            pqc_sig=psig,
            trad_pk=tpk,
            pqc_pk=ppk,
        )

        exp_oracle = compute_reference_oracle(
            op_code=opcode,
            sig_type=stype,
            request_bytes=req,
            trad_sig_len=len(tsig),
            pqc_sig_len=len(psig),
            trad_pk_len=len(tpk),
            pqc_pk_len=len(ppk),
        )
        exp_res = exp_oracle.pack()

        act_res, dt_ms = run_dr42_composite_sig_on_aie2(
            op_code=opcode,
            sig_type=stype,
            trad_sig_len=len(tsig),
            pqc_sig_len=len(psig),
            trad_pk_len=len(tpk),
            pqc_pk_len=len(ppk),
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

    print("\n" + "=" * 75)
    print(f"TOTAL: {completed}/{completed} executed, {passed}/{completed} bit-exact PASS")
    print("=" * 75)

    ended_at = datetime.now(timezone.utc).isoformat()
    result_payload = {
        "gate_id": "DR42",
        "status": "PASS" if (completed == 25 and passed == 25) else "FAIL",
        "hardware_execution": True,
        "backend": BACKEND_LABEL,
        "cases_selected": completed,
        "cases_executed": completed,
        "cases_passed": passed,
        "cases_failed": completed - passed,
        "started_at": started_at,
        "ended_at": ended_at,
        "device_info": device_info,
        "kernel_artifact": artifact_info,
        "case_results": case_results,
        "test_buffers": test_buffers,
    }

    print(RESULT_START_MARKER)
    print(json.dumps(result_payload, indent=2))
    print(RESULT_END_MARKER)

    return 0 if (completed == 25 and passed == 25) else 1


if __name__ == "__main__":
    sys.exit(main())
