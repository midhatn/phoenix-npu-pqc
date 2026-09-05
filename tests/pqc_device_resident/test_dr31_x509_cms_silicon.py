# SPDX-License-Identifier: Apache-2.0
"""Milestone DR31: NIST SP 800-208 / RFC 5280 / RFC 5652 X.509 Post-Quantum Certificates
& Hybrid CMS Co-Processor Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: RFC 5280, RFC 5652, NIST SP 800-208, RFC 9688 / IETF LAMPS WG.
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

from phoenix_sdr_dsp.pqc.dr31_x509_cms_abi import (
    ALGO_ML_DSA_44,
    ALGO_ML_DSA_65,
    ALGO_ML_DSA_87,
    ALGO_SLH_DSA_SHAKE_128S,
    ALGO_LMS_SHA256_M32_H10,
    ALGO_HYBRID_ED25519_MLDSA65,
    ALGO_ML_KEM_768,
    ALGO_ML_KEM_1024,
    FLAG_IS_CA,
    FLAG_HAS_SIGNED_ATTRS,
)
from phoenix_sdr_dsp.pqc.dr31_x509_cms_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    x509_pqc_verify_on_aie2,
    x509_hybrid_verify_on_aie2,
    cms_signed_data_verify_on_aie2,
    cms_enveloped_unwrap_on_aie2,
    x509_chain_step_verify_on_aie2,
    ref_x509_compute_fingerprint,
    ref_verify_pqc_signature,
    ref_verify_classical_signature,
    ref_unwrap_cms_cek,
    make_valid_pqc_signature,
    make_valid_classical_signature,
    make_wrapped_cek,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR31: NIST SP 800-208 / RFC 5280 / RFC 5652 X.509 PQC & Hybrid CMS Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr31-x509-cms)")
    print("Standards: RFC 5280, RFC 5652, NIST SP 800-208, RFC 9688")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x31313131)

    # Preflight probe on hardware
    try:
        dummy_tbs = bytes(32)
        dummy_pk = bytes(1952)
        dummy_sig = bytes(3293)
        x509_pqc_verify_on_aie2(ALGO_ML_DSA_65, dummy_tbs, dummy_pk, dummy_sig)
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr31-x509-cms:unavailable ({type(exc).__name__}: {exc})")
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

    # 1. Gate 1: Pure PQC X.509 Certificate Verification (6 cases)
    print("\n--- Gate 1: Pure PQC X.509 Certificate Verification (6 cases) ---")
    pqc_specs = [
        (ALGO_ML_DSA_44,          1312, 2420, "mldsa44_valid", True),
        (ALGO_ML_DSA_65,          1952, 3293, "mldsa65_valid", True),
        (ALGO_ML_DSA_87,          2592, 4595, "mldsa87_valid", True),
        (ALGO_SLH_DSA_SHAKE_128S, 64,   7856, "slhdsa_valid",  True),
        (ALGO_LMS_SHA256_M32_H10, 64,   128,  "lms_valid",     True),
        (ALGO_ML_DSA_65,          1952, 3293, "mldsa65_tamper", False),
    ]

    for algo_id, pk_len, sig_len, name, is_valid_expected in pqc_specs:
        cid = f"dr31-gate1-pqc-{name}"
        tbs = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        pk = bytes(rng.integers(0, 256, size=pk_len, dtype=np.uint8))
        sig = make_valid_pqc_signature(algo_id, tbs, pk, sig_len)

        if not is_valid_expected:
            bad_sig = bytearray(sig)
            bad_sig[0] ^= 0x01
            sig = bytes(bad_sig)

        res, dt_ms = x509_pqc_verify_on_aie2(algo_id, tbs, pk, sig)
        act_valid = res["is_valid"]
        exp_valid = ref_verify_pqc_signature(algo_id, tbs, pk, sig)
        act_fp = res["fingerprint"]
        exp_fp = ref_x509_compute_fingerprint(tbs, pk, sig)

        ok_valid = (act_valid == exp_valid)
        ok_fp = (act_fp == exp_fp)
        case_ok = bool(ok_valid and ok_fp and (act_valid == is_valid_expected))

        completed += 1
        if case_ok:
            passed += 1
        case_results.append({
            "case_id": cid,
            "status": "PASS" if case_ok else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_fp.hex(),
            "actual_hex": act_fp.hex(),
        })
        print(f"  {cid}: {'PASS' if case_ok else 'FAIL'} ({dt_ms:.2f} ms)")

    # 2. Gate 2: Hybrid / Composite X.509 Certificate Verification (5 cases)
    print("\n--- Gate 2: Hybrid / Composite X.509 Certificate Verification (5 cases) ---")
    hybrid_specs = [
        ("both_valid",         True,  True,  True),
        ("classical_tampered", False, True,  False),
        ("pqc_tampered",       True,  False, False),
        ("both_tampered",      False, False, False),
        ("all_zero_signatures", False, False, False),
    ]

    for name, class_valid, pqc_valid, exp_composite in hybrid_specs:
        cid = f"dr31-gate2-hybrid-{name}"
        tbs = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        pqc_pk = bytes(rng.integers(0, 256, size=1952, dtype=np.uint8))
        pqc_sig = make_valid_pqc_signature(ALGO_ML_DSA_65, tbs, pqc_pk, 3293)
        ed_pk = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        ed_sig = make_valid_classical_signature(tbs, ed_pk)

        if name == "all_zero_signatures":
            pqc_sig = bytes(3293)
            ed_sig = bytes(64)
        else:
            if not class_valid:
                bad_ed = bytearray(ed_sig)
                bad_ed[0] ^= 0x01
                ed_sig = bytes(bad_ed)
            if not pqc_valid:
                bad_pqc = bytearray(pqc_sig)
                bad_pqc[0] ^= 0x01
                pqc_sig = bytes(bad_pqc)

        res, dt_ms = x509_hybrid_verify_on_aie2(
            tbs, ALGO_ML_DSA_65, pqc_pk, pqc_sig, ed_pk, ed_sig
        )
        act_comp = res["is_valid"]
        act_fp = res["fingerprint"]
        exp_fp = ref_x509_compute_fingerprint(tbs, pqc_pk, pqc_sig)

        ok_comp = (act_comp == exp_composite)
        ok_fp = (act_fp == exp_fp)
        case_ok = bool(ok_comp and ok_fp)

        completed += 1
        if case_ok:
            passed += 1
        case_results.append({
            "case_id": cid,
            "status": "PASS" if case_ok else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_fp.hex(),
            "actual_hex": act_fp.hex(),
        })
        print(f"  {cid}: {'PASS' if case_ok else 'FAIL'} ({dt_ms:.2f} ms)")

    # 3. Gate 3: CMS SignedData Verification (5 cases)
    print("\n--- Gate 3: CMS SignedData Verification (5 cases) ---")
    cms_specs = [
        (ALGO_ML_DSA_65, 1952, 3293, "valid_content_signer", False, True),
        (ALGO_ML_DSA_87, 2592, 4595, "valid_signed_attrs",   True,  True),
        (ALGO_ML_DSA_65, 1952, 3293, "mismatch_attrs_tamper", True,  False),
        (ALGO_ML_DSA_65, 1952, 3293, "corrupt_signer_sig",   False, False),
        (ALGO_ML_DSA_65, 1952, 3293, "all_zero_public_key",  False, False),
    ]

    for algo_id, pk_len, sig_len, name, use_attrs, exp_valid in cms_specs:
        cid = f"dr31-gate3-cms-signed-{name}"
        content_digest = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        signer_pk = bytes(rng.integers(0, 256, size=pk_len, dtype=np.uint8))

        signed_attrs = b""
        if use_attrs:
            # First 32 bytes contain content_digest, followed by metadata
            signed_attrs = content_digest + bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
            tbs_for_sig = signed_attrs
        else:
            tbs_for_sig = content_digest

        signer_sig = make_valid_pqc_signature(algo_id, tbs_for_sig, signer_pk, sig_len)

        if name == "mismatch_attrs_tamper":
            # Tamper with content digest in attributes
            bad_attrs = bytearray(signed_attrs)
            bad_attrs[0] ^= 0xFF
            signed_attrs = bytes(bad_attrs)
        elif name == "corrupt_signer_sig":
            bad_sig = bytearray(signer_sig)
            bad_sig[0] ^= 0x01
            signer_sig = bytes(bad_sig)
        elif name == "all_zero_public_key":
            signer_pk = bytes(pk_len)

        res, dt_ms = cms_signed_data_verify_on_aie2(
            algo_id, content_digest, signer_pk, signer_sig, signed_attrs
        )
        act_valid = res["is_valid"]
        case_ok = bool(act_valid == exp_valid)

        completed += 1
        if case_ok:
            passed += 1
        case_results.append({
            "case_id": cid,
            "status": "PASS" if case_ok else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": "01" if exp_valid else "00",
            "actual_hex": "01" if act_valid else "00",
        })
        print(f"  {cid}: {'PASS' if case_ok else 'FAIL'} ({dt_ms:.2f} ms)")

    # 4. Gate 4: CMS EnvelopedData KEM Decapsulation & CEK Unwrapping (5 cases)
    print("\n--- Gate 4: CMS EnvelopedData KEM Decapsulation & CEK Unwrapping (5 cases) ---")
    kem_specs = [
        (ALGO_ML_KEM_768,  1088, "mlkem768_valid_unwrap",  True),
        (ALGO_ML_KEM_1024, 1568, "mlkem1024_valid_unwrap", True),
        (ALGO_ML_KEM_768,  1088, "corrupted_kem_ct",       False),
        (ALGO_ML_KEM_768,  1088, "corrupted_auth_tag",      False),
        (ALGO_ML_KEM_768,  1088, "truncated_wrapped_cek",   False),
    ]

    for algo_id, ct_len, name, exp_valid in kem_specs:
        cid = f"dr31-gate4-cms-enveloped-{name}"
        kem_ct = bytes(rng.integers(0, 256, size=ct_len, dtype=np.uint8))
        plain_cek = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        wrapped_cek = make_wrapped_cek(kem_ct, plain_cek)

        if name == "corrupted_kem_ct":
            bad_ct = bytearray(kem_ct)
            bad_ct[0] ^= 0xFF
            kem_ct = bytes(bad_ct)
        elif name == "corrupted_auth_tag":
            bad_wrap = bytearray(wrapped_cek)
            bad_wrap[-1] ^= 0xFF
            wrapped_cek = bytes(bad_wrap)
        elif name == "truncated_wrapped_cek":
            wrapped_cek = wrapped_cek[:30]

        res, dt_ms = cms_enveloped_unwrap_on_aie2(algo_id, kem_ct, wrapped_cek)
        act_valid = res["is_valid"]
        act_cek = res["cek"]

        ok_valid = (act_valid == exp_valid)
        if exp_valid:
            ok_cek = (act_cek == plain_cek)
        else:
            ok_cek = (len(act_cek) == 0)

        case_ok = bool(ok_valid and ok_cek)

        completed += 1
        if case_ok:
            passed += 1
        case_results.append({
            "case_id": cid,
            "status": "PASS" if case_ok else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": plain_cek.hex() if exp_valid else "",
            "actual_hex": act_cek.hex() if exp_valid else "",
        })
        print(f"  {cid}: {'PASS' if case_ok else 'FAIL'} ({dt_ms:.2f} ms)")

    # 5. Gate 5: X.509 Certificate Delegation & Hierarchy (4 cases)
    print("\n--- Gate 5: X.509 Certificate Delegation & Hierarchy (4 cases) ---")
    chain_specs = [
        (True,  True,  "intermediate_ca_valid_delegation"),
        (False, True,  "non_ca_cert_illegal_delegation"),
        (True,  True,  "root_ca_self_signed_valid"),
        (True,  False, "ca_cert_tampered_signature"),
    ]

    for is_ca, sig_valid, name in chain_specs:
        cid = f"dr31-gate5-chain-{name}"
        tbs = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        ca_pk = bytes(rng.integers(0, 256, size=1952, dtype=np.uint8))
        sig = make_valid_pqc_signature(ALGO_ML_DSA_65, tbs, ca_pk, 3293)

        if not sig_valid:
            bad_sig = bytearray(sig)
            bad_sig[0] ^= 0x01
            sig = bytes(bad_sig)

        res, dt_ms = x509_chain_step_verify_on_aie2(
            ALGO_ML_DSA_65, is_ca, tbs, ca_pk, sig
        )
        act_valid = res["is_valid"]
        exp_valid = bool(is_ca and sig_valid)
        act_fp = res["fingerprint"]
        exp_fp = ref_x509_compute_fingerprint(tbs, ca_pk, sig)

        ok_valid = (act_valid == exp_valid)
        ok_fp = (act_fp == exp_fp) if is_ca else True
        case_ok = bool(ok_valid and ok_fp)

        completed += 1
        if case_ok:
            passed += 1
        case_results.append({
            "case_id": cid,
            "status": "PASS" if case_ok else "FAIL",
            "runtime_ms": round(dt_ms, 3),
        })
        test_buffers.append({
            "case_id": cid,
            "expected_hex": exp_fp.hex() if is_ca else "",
            "actual_hex": act_fp.hex() if is_ca else "",
        })
        print(f"  {cid}: {'PASS' if case_ok else 'FAIL'} ({dt_ms:.2f} ms)")

    # Produce structured output
    ended_at = datetime.now(timezone.utc).isoformat()
    total_selected = len(case_results)
    total_executed = completed
    total_matching = passed
    total_failing = completed - passed

    gate_record = {
        "gate_id": "dr31-x509-cms:silicon",
        "backend": BACKEND_LABEL,
        "started_at": started_at,
        "ended_at": ended_at,
        "cases_selected": total_selected,
        "cases_executed": total_executed,
        "cases_matching": total_matching,
        "cases_failing": total_failing,
        "cases_skipped": 0,
        "cases_xfailed": 0,
        "device_info": device_info,
        "artifact_info": artifact_info,
        "case_results": case_results,
        "test_buffers": test_buffers,
    }

    print("\n" + RESULT_START_MARKER)
    print(json.dumps(gate_record, indent=2))
    print(RESULT_END_MARKER)

    print(f"\nSummary: {passed}/{completed} test cases matched oracles bit-exactly on AIE2.")
    return 0 if (passed == completed and completed == 25) else 1


if __name__ == "__main__":
    sys.exit(main())
