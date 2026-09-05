# SPDX-License-Identifier: Apache-2.0
"""Milestone DR34: Hardware Root of Trust, TCG DICE / TPM Attestation & Enclave Security Boundaries Silicon Validation Suite.
Target: AMD Phoenix NPU (AIE2 / XDNA1).
Standards: TCG DICE Attestation Architecture v1.1, TCG TPM 2.0, NIST FIPS 204.
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

from phoenix_sdr_dsp.pqc.dr34_dice_tpm_abi import (
    MAGIC_DESC_DR34,
    MODE_DICE_DERIVE_CDI,
    MODE_DICE_EXTEND_PCR,
    MODE_DICE_GENERATE_QUOTE,
    MODE_DICE_VERIFY_QUOTE,
    MODE_DICE_ENCLAVE_SEAL,
    PCR_0_FIRMWARE_BASE,
    PCR_1_TILE_DESCRIPTOR,
    PCR_2_SECURITY_CONFIG,
    PCR_3_RUNTIME_CALLER,
    PCR_4_EXT_ORACLE_HASH,
    PCR_5_ENTROPY_STATE,
    PCR_6_KEY_LIFECYCLE,
    PCR_7_ATTESTATION_NONCE,
    PCR_COUNT,
    STATUS_SUCCESS,
    REQ_TOTAL_BYTES,
    DESC_TOTAL_BYTES,
    RESULT_TOTAL_BYTES,
    pack_dr34_descriptor,
    pack_dr34_request,
    unpack_dr34_result,
    reference_dr34_oracle,
)
from phoenix_sdr_dsp.pqc.dr34_dice_tpm_graph import (
    BACKEND_LABEL,
    get_kernel_artifact_info,
    run_dr34_dice_tpm_on_aie2,
    NativeBackendUnavailable,
)

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"


def main() -> int:
    print("=" * 75)
    print("DR34: Hardware Root of Trust, TCG DICE / TPM Attestation Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr34-dice-tpm)")
    print("Standards: TCG DICE v1.1, TCG TPM 2.0, NIST FIPS 204")
    print("=" * 75)

    started_at = datetime.now(timezone.utc).isoformat()
    rng = np.random.default_rng(seed=0x34343434)

    # Preflight hardware probe
    try:
        dummy_meas = bytes(32)
        dummy_uds = bytes(32)
        run_dr34_dice_tpm_on_aie2(
            op_mode=MODE_DICE_DERIVE_CDI,
            measurement=dummy_meas,
            uds_key=dummy_uds,
        )
    except NativeBackendUnavailable as exc:
        print(f"Backend: dr34-dice-tpm:unavailable ({type(exc).__name__}: {exc})")
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

    # 1. Gate 1: TCG DICE Compound Device Identifier (CDI) Derivation on AIE2 (6 cases)
    print("\n--- Gate 1: TCG DICE CDI Derivation (6 cases) ---")
    gate1_cases = [
        ("zeros", bytes(32), bytes(32)),
        ("base_identity", bytes([1] * 32), bytes([2] * 32)),
        ("firmware_stage1", bytes([0xAA] * 32), bytes([0x55] * 32)),
        ("random_uds_a", bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8))),
        ("random_uds_b", bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8))),
        ("random_uds_c", bytes(rng.integers(0, 256, size=32, dtype=np.uint8)), bytes(rng.integers(0, 256, size=32, dtype=np.uint8))),
    ]

    for name, uds, meas in gate1_cases:
        cid = f"dr34-gate1-dice-cdi-{name}"
        seq = completed + 1
        desc = pack_dr34_descriptor(op_mode=MODE_DICE_DERIVE_CDI, seq_id=seq)
        req = pack_dr34_request(measurement=meas, uds_key=uds, seq_id=seq)
        exp_res = reference_dr34_oracle(desc, req)

        act_res, dt_ms = run_dr34_dice_tpm_on_aie2(
            op_mode=MODE_DICE_DERIVE_CDI,
            measurement=meas,
            uds_key=uds,
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

    # 2. Gate 2: Hardware PCR Measurement Register Extension (7 cases)
    print("\n--- Gate 2: Hardware PCR Measurement Register Extension (7 cases) ---")
    pcr_indices = [
        (PCR_0_FIRMWARE_BASE, "pcr0_firmware"),
        (PCR_1_TILE_DESCRIPTOR, "pcr1_descriptor"),
        (PCR_2_SECURITY_CONFIG, "pcr2_security"),
        (PCR_3_RUNTIME_CALLER, "pcr3_caller"),
        (PCR_4_EXT_ORACLE_HASH, "pcr4_oracle"),
        (PCR_5_ENTROPY_STATE, "pcr5_entropy"),
        (PCR_6_KEY_LIFECYCLE, "pcr6_lifecycle"),
    ]

    for pcr_idx, name in pcr_indices:
        cid = f"dr34-gate2-pcr-extend-{name}"
        seq = completed + 1
        meas = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        init_bank = [bytes([p + 1] * 32) for p in range(8)]
        mask = 0xFF

        desc = pack_dr34_descriptor(
            op_mode=MODE_DICE_EXTEND_PCR,
            pcr_index=pcr_idx,
            pcr_mask=mask,
            seq_id=seq,
        )
        req = pack_dr34_request(
            measurement=meas,
            initial_pcr_bank=init_bank,
            seq_id=seq,
        )
        exp_res = reference_dr34_oracle(desc, req)

        act_res, dt_ms = run_dr34_dice_tpm_on_aie2(
            op_mode=MODE_DICE_EXTEND_PCR,
            pcr_index=pcr_idx,
            pcr_mask=mask,
            measurement=meas,
            initial_pcr_bank=init_bank,
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

    # 3. Gate 3: TPM 2.0 / DICE Attestation Quote Generation over PCR Masks (6 cases)
    print("\n--- Gate 3: Attestation Quote Generation (6 cases) ---")
    quote_specs = [
        (0x01, "mask_pcr0"),
        (0x03, "mask_pcr0_1"),
        (0x07, "mask_pcr0_1_2"),
        (0x0F, "mask_pcr0_3"),
        (0x3F, "mask_pcr0_5"),
        (0xFF, "mask_pcr_all"),
    ]

    for mask, name in quote_specs:
        cid = f"dr34-gate3-quote-gen-{name}"
        seq = completed + 1
        nonce = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        pcr_bank = [bytes([p * 7 + 3] * 32) for p in range(8)]

        desc = pack_dr34_descriptor(
            op_mode=MODE_DICE_GENERATE_QUOTE,
            pcr_mask=mask,
            seq_id=seq,
        )
        req = pack_dr34_request(
            nonce=nonce,
            initial_pcr_bank=pcr_bank,
            seq_id=seq,
        )
        exp_res = reference_dr34_oracle(desc, req)

        act_res, dt_ms = run_dr34_dice_tpm_on_aie2(
            op_mode=MODE_DICE_GENERATE_QUOTE,
            pcr_mask=mask,
            nonce=nonce,
            initial_pcr_bank=pcr_bank,
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

    # 4. Gate 4: Attestation Quote Verification & Fail-Closed Tamper Detection (6 cases)
    print("\n--- Gate 4: Quote Verification & Fail-Closed Tamper Detection (6 cases) ---")
    verify_specs = [
        ("valid_quote_1", True, True),
        ("valid_quote_2", True, True),
        ("composite_tamper_1", False, True),
        ("composite_tamper_2", False, True),
        ("signature_tamper_1", True, False),
        ("signature_tamper_2", True, False),
    ]

    for name, comp_valid, sig_valid in verify_specs:
        cid = f"dr34-gate4-quote-verify-{name}"
        seq = completed + 1
        mask = 0x0F
        nonce = bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        pcr_bank = [bytes([p * 11 + 5] * 32) for p in range(8)]

        # Get golden composite
        desc_gen = pack_dr34_descriptor(op_mode=MODE_DICE_GENERATE_QUOTE, pcr_mask=mask, seq_id=seq)
        req_gen = pack_dr34_request(nonce=nonce, initial_pcr_bank=pcr_bank, seq_id=seq)
        golden_res = reference_dr34_oracle(desc_gen, req_gen)
        golden_comp = unpack_dr34_result(golden_res)["composite_digest"]

        exp_composite = golden_comp if comp_valid else bytes(rng.integers(0, 256, size=32, dtype=np.uint8))
        sig = bytes([0x01] * 64) if sig_valid else (b"\xFF" + bytes([0x00] * 63))

        desc_ver = pack_dr34_descriptor(op_mode=MODE_DICE_VERIFY_QUOTE, pcr_mask=mask, seq_id=seq)
        req_ver = pack_dr34_request(
            nonce=nonce,
            expected_composite=exp_composite,
            initial_pcr_bank=pcr_bank,
            signature=sig,
            seq_id=seq,
        )
        exp_res = reference_dr34_oracle(desc_ver, req_ver)

        act_res, dt_ms = run_dr34_dice_tpm_on_aie2(
            op_mode=MODE_DICE_VERIFY_QUOTE,
            pcr_mask=mask,
            nonce=nonce,
            expected_composite=exp_composite,
            initial_pcr_bank=pcr_bank,
            signature=sig,
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

    ended_at = datetime.now(timezone.utc).isoformat()

    print("\n" + "=" * 75)
    print(f"DR34 Silicon Gate Summary: {passed}/{completed} cases passed ({passed/completed*100:.1f}%)")
    print("=" * 75)

    payload = {
        "dr_id": "DR34",
        "gate_name": "dr34-dice-tpm:silicon",
        "backend": BACKEND_LABEL,
        "device_info": device_info,
        "artifact_info": artifact_info,
        "started_at": started_at,
        "ended_at": ended_at,
        "cases_total": completed,
        "cases_passed": passed,
        "cases_failed": completed - passed,
        "case_results": case_results,
        "test_buffers": test_buffers,
    }

    print(RESULT_START_MARKER)
    print(json.dumps(payload, indent=2))
    print(RESULT_END_MARKER)

    return 0 if (passed == completed and completed == 25) else 1


if __name__ == "__main__":
    sys.exit(main())
