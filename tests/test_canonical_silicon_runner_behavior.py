# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import run_all_silicon_tests as runner
from run_all_silicon_tests import (
    EXTENSION_GATES,
    GATES,
    NativeGate,
    RESULT_START_MARKER,
    RESULT_END_MARKER,
    STATUS_BLOCKED,
    STATUS_FAIL,
    STATUS_MISSING,
    STATUS_SELF_REPORTED_UNVERIFIED,
    STATUS_TIMEOUT,
    CaseResult,
    execute_suite,
    extract_canonical_framed_record,
    parse_gate_output,
    run_single_gate,
    scan_diagnostic_markers,
    verify_execution_environment,
)


def _make_valid_record(
    gate_id: str = "DR0",
    expected_count: int = 24,
    artifact_rel: str = "phoenix_sdr_dsp/pqc/kernels/m33_product_graph.cc",
    artifact_sha: str | None = None,
    dispatches: int = 24,
    exit_code: int = 0,
    started_at: str | None = None,
    ended_at: str | None = None,
    execution_nonce: str | None = "test_nonce_0123456789abcdef",
) -> dict[str, object]:
    """Construct a schema-compliant self-reported claim fixture with synthetic device/test values."""
    cases = [{"case_id": f"case_{i:03d}", "status": "PASS"} for i in range(expected_count)]
    if artifact_sha is None:
        art_path = runner.REPO_ROOT / artifact_rel
        if art_path.is_file():
            artifact_sha = hashlib.sha256(art_path.read_bytes()).hexdigest()
        else:
            artifact_sha = "678f1116813f38b1356518fd601060934d8c2d5682c935ffdad5364e0ad6ca48"

    now = datetime.now(timezone.utc)
    st = started_at or now.isoformat()
    en = ended_at or (now + timedelta(seconds=1)).isoformat()

    rec: dict[str, object] = {
        "schema_version": 1,
        "gate_id": gate_id,
        "execution_boundary": "[ON-TILE SILICON]",
        "evidence_class": "BIT_EXACT_PHYSICAL_SILICON",
        "device": {
            "device_name": "AMD Phoenix APU (Ryzen 7940HS) [SYNTHETIC TEST FIXTURE]",
            "device_id": "0000:c4:00.5",
            "driver": "32.0.20102.3930",
            "firmware": "1.5.5.391",
        },
        "artifact": {
            "path": artifact_rel,
            "sha256": artifact_sha,
        },
        "dispatch": {
            "physical_dispatches": dispatches,
            "completed": True,
        },
        "cases_selected": expected_count,
        "cases_executed": expected_count,
        "cases": cases,
        "exit_code": exit_code,
        "started_at": st,
        "ended_at": en,
        "child_pid": 12345,
    }
    if execution_nonce is not None:
        rec["execution_nonce"] = execution_nonce
    return rec


def _make_dr0_test_buffers(corrupt_index: int | None = None) -> list[dict[str, object]]:
    """Generate 24 authentic DR0 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_m33_product_dr0 import DIRECTED_VECTORS, randomized_vectors
    from phoenix_sdr_dsp.pqc import abi
    buffers: list[dict[str, object]] = []
    all_vecs = (*DIRECTED_VECTORS, *randomized_vectors())
    for idx, (name, a, b) in enumerate(all_vecs):
        expected = abi.reference_negacyclic_product(a, b)
        output_c = list(expected)
        if corrupt_index is not None and idx == corrupt_index:
            output_c[0] = (output_c[0] + 1) % abi.Q
        buffers.append({
            "case_name": name,
            "input_a": a,
            "input_b": b,
            "output_c": output_c,
        })
    return buffers


def _make_dr1_test_buffers(
    corrupt_index: int | None = None,
    corrupt_fingerprint_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 33 authentic DR1 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.dr1_reference import expanda_rejntt_reference
    from tests.pqc_device_resident.test_dr1_mldsa44_rejntt import PRE_SILICON_CORPUS, _coefficient_digest
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr1_case_{idx:03d}_{case.label}"
        expected = expanda_rejntt_reference(case.rho, case.j, case.i)
        out_coeffs = list(expected.coefficients)
        if corrupt_index is not None and idx == corrupt_index:
            out_coeffs[0] = (out_coeffs[0] + 1) % 8380417
        fp = _coefficient_digest(out_coeffs)
        if corrupt_fingerprint_index is not None and idx == corrupt_fingerprint_index:
            fp = "0" * 64
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "rho_hex": case.rho.hex(),
            "j": case.j,
            "i": case.i,
            "request_id": case.request_id,
            "output_coefficients": out_coeffs,
            "fingerprint_sha256": fp,
        })
    return buffers


def _make_dr2a_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 13 authentic DR2a test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.dr2a_reference import samplentt_reference
    from tests.pqc_device_resident.test_dr2_mlkem512_samplentt import PRE_SILICON_CORPUS
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr2a_case_{idx:03d}_{case.label}"
        expected = samplentt_reference(case.rho, case.j, case.i)
        out_coeffs = list(expected.coefficients)
        if corrupt_index is not None and idx == corrupt_index:
            out_coeffs[0] = (out_coeffs[0] + 1) % 3329
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "rho_hex": case.rho.hex(),
            "j": case.j,
            "i": case.i,
            "request_id": case.request_id,
            "output_coefficients": out_coeffs,
        })
    return buffers


def _make_dr2b_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 13 authentic DR2b test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.dr2b_reference import noise_ntt_reference
    from tests.pqc_device_resident.test_dr2b_mlkem512_noise_ntt import PRE_SILICON_CORPUS
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr2b_case_{idx:03d}_{case.label}"
        expected = list(noise_ntt_reference(case.sigma, case.counter))
        out_coeffs = list(expected)
        if corrupt_index is not None and idx == corrupt_index:
            out_coeffs[0] = (out_coeffs[0] + 1) % 3329
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "sigma_hex": case.sigma.hex(),
            "counter": case.counter,
            "request_id": case.request_id,
            "output_coefficients": out_coeffs,
        })
    return buffers


def _make_dr2c_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 11 authentic DR2c test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.dr2c_reference import keygen_row_reference
    from tests.pqc_device_resident.test_dr2c_mlkem512_keygen_row import PRE_SILICON_CORPUS
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr2c_case_{idx:03d}_{case.label}"
        expected = list(keygen_row_reference(case.rho, case.sigma, case.row_index))
        out_coeffs = list(expected)
        if corrupt_index is not None and idx == corrupt_index:
            out_coeffs[0] = (out_coeffs[0] + 1) % 3329
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "rho_hex": case.rho.hex(),
            "sigma_hex": case.sigma.hex(),
            "row_index": case.row_index,
            "request_id": case.request_id,
            "output_coefficients": out_coeffs,
        })
    return buffers


def _make_dr2d_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR2d test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr2d_case_{idx:03d}_{case.label}"
        tc_id = int(case.label[-2:])
        expected_ek, expected_dk = ACVP_EXPECTED[tc_id]
        ek_bytes = bytearray(expected_ek)
        dk_bytes = bytearray(expected_dk)
        if corrupt_index is not None and idx == corrupt_index:
            ek_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "tc_id": tc_id,
            "d_hex": case.d.hex(),
            "request_id": case.request_id,
            "ek_pke_hex": bytes(ek_bytes).hex(),
            "dk_pke_hex": bytes(dk_bytes).hex(),
        })
    return buffers


def _make_dr3_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR3 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr3_mlkem512_kpke_encrypt import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr3_case_{idx:03d}_{case.label}"
        expected_c = ACVP_EXPECTED[case.tc_id]
        c_bytes = bytearray(expected_c)
        if corrupt_index is not None and idx == corrupt_index:
            c_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "tc_id": case.tc_id,
            "ek_hex": case.ek.hex(),
            "m_hex": case.m.hex(),
            "r_hex": case.r.hex(),
            "request_id": case.request_id,
            "c_hex": bytes(c_bytes).hex(),
        })
    return buffers


def _make_dr4_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR4 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr4_mlkem512_kpke_decrypt import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr4_case_{idx:03d}_{case.label}"
        expected_m = ACVP_EXPECTED[case.tc_id]
        m_bytes = bytearray(expected_m)
        if corrupt_index is not None and idx == corrupt_index:
            m_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "tc_id": case.tc_id,
            "dk_pke_hex": case.dk_pke.hex(),
            "c_hex": case.c.hex(),
            "request_id": case.request_id,
            "m_hex": bytes(m_bytes).hex(),
        })
    return buffers


def _make_dr5_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR5 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr5_mlkem512_keygen import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr5_case_{idx:03d}_{case.label}"
        expected_ek, expected_dk = ACVP_EXPECTED[case.tc_id]
        ek_bytes = bytearray(expected_ek)
        dk_bytes = bytearray(expected_dk)
        if corrupt_index is not None and idx == corrupt_index:
            ek_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "tc_id": case.tc_id,
            "d_hex": case.d.hex(),
            "z_hex": case.z.hex(),
            "request_id": case.request_id,
            "ek_hex": bytes(ek_bytes).hex(),
            "dk_hex": bytes(dk_bytes).hex(),
        })
    return buffers


def _make_dr6_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR6 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr6_mlkem512_encaps import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr6_case_{idx:03d}_{case.label}"
        expected_c, expected_k = ACVP_EXPECTED[case.tc_id]
        c_bytes = bytearray(expected_c)
        k_bytes = bytearray(expected_k)
        if corrupt_index is not None and idx == corrupt_index:
            c_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "tc_id": case.tc_id,
            "ek_hex": case.ek.hex(),
            "m_hex": case.m.hex(),
            "request_id": case.request_id,
            "c_hex": bytes(c_bytes).hex(),
            "k_hex": bytes(k_bytes).hex(),
        })
    return buffers


def _make_dr7_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR7 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr7_mlkem512_decaps import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr7_case_{idx:03d}_{case.label}"
        expected_k = ACVP_EXPECTED[case.tc_id]
        k_bytes = bytearray(expected_k)
        if corrupt_index is not None and idx == corrupt_index:
            k_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.label,
            "tc_id": case.tc_id,
            "dk_hex": case.dk.hex(),
            "c_hex": case.c.hex(),
            "request_id": case.request_id,
            "k_hex": bytes(k_bytes).hex(),
        })
    return buffers


def _make_dr8_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 75 authentic DR8 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr8_mlkem_unified import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr8_case_{idx:03d}_{case.param_set}_{case.tc_id}"
        expected_k = ACVP_EXPECTED[case.tc_id]
        k_bytes = bytearray(expected_k)
        if corrupt_index is not None and idx == corrupt_index:
            k_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": f"{case.param_set}_{case.tc_id}",
            "tc_id": case.tc_id,
            "param_set": case.param_set,
            "request_id": case.request_id,
            "k_hex": bytes(k_bytes).hex(),
        })
    return buffers


def _make_dr9_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 122 authentic DR9 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr9_fips202 import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr9_case_{idx:03d}_{case.tc_id}"
        expected_digest = ACVP_EXPECTED[case.tc_id]
        digest_bytes = bytearray(expected_digest)
        if corrupt_index is not None and idx == corrupt_index:
            digest_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.tc_id,
            "tc_id": case.tc_id,
            "func_name": case.func_name,
            "msg_hex": case.msg.hex(),
            "out_len": case.out_len,
            "request_id": case.request_id,
            "digest_hex": bytes(digest_bytes).hex(),
        })
    return buffers


def _make_dr10_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 40 authentic DR10 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr10_sealed_lifecycle import (
        EXPECTED_RESULTS,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr10_case_{idx:03d}_{case.name}"
        status, active_slot = EXPECTED_RESULTS[case.name]
        if corrupt_index is not None and idx == corrupt_index:
            status ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.name,
            "name": case.name,
            "request_id": case.request_id,
            "status": status,
            "active_slot": active_slot,
            "crc": 0x12345678,
        })
    return buffers


def _make_dr11_test_buffers(
    corrupt_index: int | None = None,
) -> list[dict[str, object]]:
    """Generate 25 authentic DR11 test buffers for parent oracle verification tests."""
    from tests.pqc_device_resident.test_dr11_mldsa44_keygen import (
        ACVP_EXPECTED,
        PRE_SILICON_CORPUS,
    )
    buffers: list[dict[str, object]] = []
    for idx, case in enumerate(PRE_SILICON_CORPUS):
        case_id = f"dr11_case_{idx:03d}_{case.tc_id}"
        exp_pk, exp_sk = ACVP_EXPECTED[case.tc_id]
        pk_bytes = bytearray(exp_pk)
        sk_bytes = bytearray(exp_sk)
        if corrupt_index is not None and idx == corrupt_index:
            pk_bytes[0] ^= 0xFF
        buffers.append({
            "case_id": case_id,
            "case_label": case.tc_id,
            "tc_id": case.tc_id,
            "seed_hex": case.seed.hex(),
            "request_id": case.request_id,
            "pk_hex": bytes(pk_bytes).hex(),
            "sk_hex": bytes(sk_bytes).hex(),
        })
    return buffers


def _wrap_record_in_stdout(record: dict[str, object], preamble: str = "") -> str:
    serialized = json.dumps(record, indent=2)
    return f"{preamble}\n{RESULT_START_MARKER}\n{serialized}\n{RESULT_END_MARKER}\n"


class CanonicalSiliconRunnerBehaviorTests(unittest.TestCase):
    def test_gate_count_and_case_total(self) -> None:
        self.assertEqual(len(GATES), 19)
        self.assertEqual(GATES[0].gate_id, "DR0")
        self.assertEqual(GATES[-1].gate_id, "DR15")
        self.assertEqual(sum(gate.expected_total for gate in GATES), 736)

    def test_extension_gate_count_and_case_total(self) -> None:
        self.assertEqual(len(EXTENSION_GATES), 5)
        self.assertEqual(EXTENSION_GATES[0].gate_id, "DR16")
        self.assertEqual(EXTENSION_GATES[-1].gate_id, "DR27")
        self.assertEqual(sum(gate.expected_total for gate in EXTENSION_GATES), 121)

    def test_all_gates_count_and_case_total(self) -> None:
        all_gates = GATES + EXTENSION_GATES
        self.assertEqual(len(all_gates), 24)
        self.assertEqual(sum(gate.expected_total for gate in all_gates), 857)

    def test_scan_diagnostic_markers(self) -> None:
        self.assertEqual(scan_diagnostic_markers("Clean silicon run"), [])
        findings = scan_diagnostic_markers("Backend: m33-dr0:unavailable\nusing fallback")
        markers = [m.lower() for _, m, _ in findings]
        self.assertIn("unavailable", markers)
        self.assertIn("fallback", markers)

    def test_well_formed_record_remains_self_reported_unverified(self) -> None:
        """A well-formed child JSON record must produce SELF_REPORTED_UNVERIFIED and success=False."""
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id=gate.gate_id, expected_count=gate.expected_total)
        stdout = _wrap_record_in_stdout(rec, "Diagnostic stdout")
        res = parse_gate_output(
            gate=gate,
            stdout=stdout,
            stderr="",
            exit_code=0,
            duration_seconds=1.0,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertEqual(res.cases_passed, 0)
        self.assertEqual(res.cases_unverified, 24)
        self.assertEqual(res.cases_failed, 0)
        self.assertIn("uncorroborated", res.error_message or "")

    def test_reject_banner_only_as_blocked(self) -> None:
        gate = GATES[0]
        banner = f"TOTAL {gate.expected_total}/{gate.expected_total} " + "PASS\n"
        stdout = f"PQC DR0\nBackend: m33-dr0:silicon\n{banner}"
        res = parse_gate_output(gate, stdout, "", 0, 0.5)
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_BLOCKED)
        self.assertEqual(res.cases_passed, 0)
        self.assertEqual(res.cases_unverified, 0)

    def test_reject_nonexistent_artifact(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            artifact_rel="nonexistent/path/kernel.xclbin",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Artifact file not found on disk", res.error_message or "")

    def test_reject_artifact_path_traversal(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            artifact_rel="../../Windows/System32/cmd.exe",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Artifact path traversal rejected", res.error_message or "")

    def test_reject_artifact_hash_mismatch(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/m33_product_graph.cc",
            artifact_sha="0000000000000000000000000000000000000000000000000000000000000000",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Artifact SHA-256 mismatch", res.error_message or "")

    def test_reject_fake_dispatch_count_zero(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24, dispatches=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("physical_dispatches must be an integer >= 1", res.error_message or "")

    def test_reject_malformed_timestamp(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            started_at="invalid-timestamp-format",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Invalid ISO timestamp format", res.error_message or "")

    def test_reject_timezone_naive_started_at(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            started_at="2026-08-31T03:00:00",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Timezone-naive timestamp rejected", res.error_message or "")

    def test_reject_timezone_naive_ended_at(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            ended_at="2026-08-31T03:00:05",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Timezone-naive timestamp rejected", res.error_message or "")

    def test_reject_reversed_timestamps(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            started_at=(now + timedelta(seconds=5)).isoformat(),
            ended_at=now.isoformat(),
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=10),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Timestamp inversion", res.error_message or "")

    def test_reject_stale_timestamps(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            started_at=(now - timedelta(days=1)).isoformat(),
            ended_at=(now - timedelta(days=1, seconds=-5)).isoformat(),
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Stale started_at", res.error_message or "")

    def test_reject_missing_cases_selected(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        del rec["cases_selected"]
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Missing required field: cases_selected", res.error_message or "")

    def test_reject_missing_cases_executed(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        del rec["cases_executed"]
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("Missing required field: cases_executed", res.error_message or "")

    def test_reject_boolean_case_count(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        rec["cases_selected"] = True
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("cases_selected must be an integer, got bool", res.error_message or "")

    def test_reject_mismatched_declared_counts(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        rec["cases_selected"] = 99
        rec["cases_executed"] = 12
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("cases_selected (99) != expected total (24)", res.error_message or "")
        self.assertIn("cases_executed (12) != cases length (24)", res.error_message or "")

    def test_evidence_validation_failure_does_not_become_cryptographic_failure(self) -> None:
        """When evidence metadata fails validation (e.g. wrong nonce), cases remain unverified claims."""
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            execution_nonce="wrong_nonce",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="expected_nonce",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertEqual(res.cases_passed, 0)
        self.assertEqual(res.cases_unverified, 24)
        self.assertEqual(res.cases_failed, 0)
        self.assertIn("execution_nonce mismatch", res.error_message or "")

    def test_reject_malformed_block_followed_by_valid_block(self) -> None:
        gate = GATES[0]
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        serialized = json.dumps(rec)
        stdout = (
            f"{RESULT_START_MARKER}\n{{ invalid_json \n{RESULT_END_MARKER}\n"
            f"{RESULT_START_MARKER}\n{serialized}\n{RESULT_END_MARKER}\n"
        )
        res = parse_gate_output(gate, stdout, "", 0, 0.5)
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_BLOCKED)
        self.assertIn("Framing delimiter anomaly: 2 start marker(s), 2 end marker(s)", res.error_message or "")

    def test_reject_unmatched_delimiters(self) -> None:
        gate = GATES[0]
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        stdout = f"{RESULT_START_MARKER}\n{json.dumps(rec)}\n"
        res = parse_gate_output(gate, stdout, "", 0, 0.5)
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_BLOCKED)
        self.assertIn("Framing delimiter anomaly", res.error_message or "")

    def test_reject_child_record_not_bound_to_execution_nonce(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR0",
            expected_count=24,
            execution_nonce="replayed_stale_nonce",
        )
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="fresh_parent_nonce_9999",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("execution_nonce mismatch", res.error_message or "")

    def test_verify_execution_environment_fails_closed(self) -> None:
        nonexistent = Path("C:/nonexistent_ironenv/Scripts/python.exe")
        ok, msg = verify_execution_environment(nonexistent)
        self.assertFalse(ok)
        self.assertIn("Configured IRON environment interpreter not found", msg)

    def test_missing_gate_file_fails_closed(self) -> None:
        fake_gate = NativeGate(
            gate_id="TEST_MISSING",
            title="Nonexistent Gate",
            script=Path("tests/pqc_device_resident/missing_gate_file_xyz.py"),
            backend_label="missing:silicon",
            expected_total=10,
        )
        res = run_single_gate(fake_gate, "python", runner.REPO_ROOT)
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_MISSING)

    def test_gate_timeout_fails_closed(self) -> None:
        gate = GATES[0]
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=1.0)):
            res = run_single_gate(gate, "python", runner.REPO_ROOT)
            self.assertFalse(res.success)
            self.assertEqual(res.status, STATUS_TIMEOUT)

    def test_execute_suite_accounting(self) -> None:
        fake_gate_1 = NativeGate("G1", "Gate 1", Path("tests/pqc_device_resident/test_m33_product_dr0.py"), "g1:silicon", 10)
        fake_gate_2 = NativeGate("G2", "Gate 2", Path("tests/pqc_device_resident/test_dr1_mldsa44_rejntt_silicon.py"), "g2:silicon", 20)
        suite = (fake_gate_1, fake_gate_2)

        def mock_run(gate: NativeGate, python_exe: str, repo_root: Path):
            return runner.GateExecutionResult(
                gate=gate,
                success=False,
                status=STATUS_SELF_REPORTED_UNVERIFIED,
                exit_code=0,
                cases_selected=gate.expected_total,
                cases_executed=gate.expected_total,
                cases_passed=0,
                cases_failed=0,
                cases_unverified=gate.expected_total,
                cases_skipped=0,
                cases_xfailed=0,
                case_results=tuple(CaseResult(f"c_{i}", "PASS") for i in range(gate.expected_total)),
                duration_seconds=0.1,
            )

        with mock.patch("run_all_silicon_tests.run_single_gate", side_effect=mock_run):
            results, elapsed = execute_suite(suite, "python", runner.REPO_ROOT, verbose=False)
            self.assertEqual(len(results), 2)
            self.assertFalse(any(r.success for r in results))
            self.assertEqual(sum(r.cases_passed for r in results), 0)
            self.assertEqual(sum(r.cases_unverified for r in results), 30)

    def test_dr0_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        rec["test_buffers"] = _make_dr0_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 24 x 256" in note for note in res.corroboration_notes))

    def test_dr0_corrupted_buffer_coefficient_fails_validation(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        # Corrupt 1 coefficient in case index 3
        rec["test_buffers"] = _make_dr0_test_buffers(corrupt_index=3)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch at lane", res.error_message or "")

    def test_dr0_truncated_test_buffers_fails_validation(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        # Pass only 23 buffers instead of 24
        rec["test_buffers"] = _make_dr0_test_buffers()[:23]
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("test_buffers length (23) != expected gate total (24)", res.error_message or "")

    def test_xcl_emulation_mode_fails_closed(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        stdout = _wrap_record_in_stdout(rec)
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            # Runner verify_execution_environment rejects emulation
            ok, msg = verify_execution_environment()
            self.assertFalse(ok)
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", msg)

            # parse_gate_output rejects emulation
            res = parse_gate_output(
                gate, stdout, "", 0, 0.5,
                parent_start_time=now - timedelta(seconds=2),
                parent_end_time=now + timedelta(seconds=2),
                execution_nonce="test_nonce_0123456789abcdef",
            )
            self.assertFalse(res.success)
            self.assertEqual(res.status, STATUS_FAIL)
            self.assertIn("XCL_EMULATION_MODE='sw_emu' is active", res.error_message or "")

    def test_invalid_child_pid_fails_validation(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        rec["child_pid"] = -1
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("child_pid must be a positive integer", res.error_message or "")

    def test_dr0_module_rejects_emulation_mode(self) -> None:
        from phoenix_sdr_dsp.pqc import m33_product_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "hw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='hw_emu'", str(ctx.exception))

    def test_xrt_ini_path_fails_closed(self) -> None:
        gate = GATES[0]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(gate_id="DR0", expected_count=24)
        stdout = _wrap_record_in_stdout(rec)
        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            # Runner verify_execution_environment rejects redirection
            ok, msg = verify_execution_environment()
            self.assertFalse(ok)
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", msg)

            # parse_gate_output rejects redirection
            res = parse_gate_output(
                gate, stdout, "", 0, 0.5,
                parent_start_time=now - timedelta(seconds=2),
                parent_end_time=now + timedelta(seconds=2),
                execution_nonce="test_nonce_0123456789abcdef",
            )
            self.assertFalse(res.success)
            self.assertEqual(res.status, STATUS_FAIL)
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini' is active", res.error_message or "")

    def test_dr0_module_rejects_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import m33_product_graph as graph
        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/custom/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/custom/xrt.ini'", str(ctx.exception))

    def test_dr1_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[1]  # DR1
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR1",
            expected_count=33,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr1_mldsa44_rejntt.cc",
            dispatches=33,
        )
        rec["test_buffers"] = _make_dr1_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 33 x 256" in note for note in res.corroboration_notes))

    def test_dr1_corrupted_coefficient_fails_validation(self) -> None:
        gate = GATES[1]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR1",
            expected_count=33,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr1_mldsa44_rejntt.cc",
            dispatches=33,
        )
        # Corrupt 1 coefficient in case index 5
        rec["test_buffers"] = _make_dr1_test_buffers(corrupt_index=5)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch at lane", res.error_message or "")

    def test_dr1_corrupted_fingerprint_fails_validation(self) -> None:
        gate = GATES[1]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR1",
            expected_count=33,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr1_mldsa44_rejntt.cc",
            dispatches=33,
        )
        # Corrupt fingerprint in case index 2
        rec["test_buffers"] = _make_dr1_test_buffers(corrupt_fingerprint_index=2)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("fingerprint mismatch", res.error_message or "")

    def test_dr1_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr1_mldsa44_rejntt_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr2a_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[2]  # DR2a
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2a",
            expected_count=13,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2_mlkem512_samplentt.cc",
            dispatches=13,
        )
        rec["test_buffers"] = _make_dr2a_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 13 x 256" in note for note in res.corroboration_notes))

    def test_dr2a_corrupted_coefficient_fails_validation(self) -> None:
        gate = GATES[2]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2a",
            expected_count=13,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2_mlkem512_samplentt.cc",
            dispatches=13,
        )
        # Corrupt 1 coefficient in case index 3
        rec["test_buffers"] = _make_dr2a_test_buffers(corrupt_index=3)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch at lane", res.error_message or "")

    def test_dr2a_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr2_mlkem512_samplentt_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr2b_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[3]  # DR2b
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2b",
            expected_count=13,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2b_mlkem512_cbd_ntt.cc",
            dispatches=13,
        )
        rec["test_buffers"] = _make_dr2b_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 13 x 256" in note for note in res.corroboration_notes))

    def test_dr2b_corrupted_coefficient_fails_validation(self) -> None:
        gate = GATES[3]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2b",
            expected_count=13,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2b_mlkem512_cbd_ntt.cc",
            dispatches=13,
        )
        # Corrupt 1 coefficient in case index 2
        rec["test_buffers"] = _make_dr2b_test_buffers(corrupt_index=2)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch at lane", res.error_message or "")

    def test_dr2b_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr2b_mlkem512_noise_ntt_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr2c_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[4]  # DR2c
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2c",
            expected_count=11,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_accumulate.cc",
            dispatches=11,
        )
        rec["test_buffers"] = _make_dr2c_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 11 x 256" in note for note in res.corroboration_notes))

    def test_dr2c_corrupted_coefficient_fails_validation(self) -> None:
        gate = GATES[4]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2c",
            expected_count=11,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_accumulate.cc",
            dispatches=11,
        )
        # Corrupt 1 coefficient in case index 1
        rec["test_buffers"] = _make_dr2c_test_buffers(corrupt_index=1)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch at lane", res.error_message or "")

    def test_dr2c_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr2c_mlkem512_keygen_row_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr2d_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[5]  # DR2d
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2d",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_seed.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr2d_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP key pairs" in note for note in res.corroboration_notes))

    def test_dr2d_corrupted_key_fails_validation(self) -> None:
        gate = GATES[5]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR2d",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_seed.cc",
            dispatches=25,
        )
        # Corrupt 1 key in case index 0
        rec["test_buffers"] = _make_dr2d_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP vector", res.error_message or "")

    def test_dr2d_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr3_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[6]  # DR3
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR3",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr3_mlkem512_kpke_encrypt_noise.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr3_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP ciphertexts" in note for note in res.corroboration_notes))

    def test_dr3_corrupted_ciphertext_fails_validation(self) -> None:
        gate = GATES[6]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR3",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr3_mlkem512_kpke_encrypt_noise.cc",
            dispatches=25,
        )
        # Corrupt 1 ciphertext in case index 0
        rec["test_buffers"] = _make_dr3_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP ciphertext", res.error_message or "")

    def test_dr3_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr3_mlkem512_kpke_encrypt_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr4_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[7]  # DR4
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR4",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr4_mlkem512_kpke_decrypt_decompress_ntt.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr4_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP decrypted messages" in note for note in res.corroboration_notes))

    def test_dr4_corrupted_message_fails_validation(self) -> None:
        gate = GATES[7]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR4",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr4_mlkem512_kpke_decrypt_decompress_ntt.cc",
            dispatches=25,
        )
        # Corrupt 1 message in case index 0
        rec["test_buffers"] = _make_dr4_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP decrypted message", res.error_message or "")

    def test_dr4_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr4_mlkem512_kpke_decrypt_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr5_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[8]  # DR5
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR5",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr5_mlkem512_keygen_seed_noise.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr5_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP key pairs" in note for note in res.corroboration_notes))

    def test_dr5_corrupted_key_fails_validation(self) -> None:
        gate = GATES[8]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR5",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr5_mlkem512_keygen_seed_noise.cc",
            dispatches=25,
        )
        # Corrupt 1 key in case index 0
        rec["test_buffers"] = _make_dr5_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP key pair", res.error_message or "")

    def test_dr5_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr5_mlkem512_keygen_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr6_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[9]  # DR6
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR6",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr6_mlkem512_encaps_derive.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr6_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP encapsulated ciphertexts and shared keys" in note for note in res.corroboration_notes))

    def test_dr6_corrupted_key_fails_validation(self) -> None:
        gate = GATES[9]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR6",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr6_mlkem512_encaps_derive.cc",
            dispatches=25,
        )
        # Corrupt 1 ciphertext/key in case index 0
        rec["test_buffers"] = _make_dr6_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP encapsulated ciphertext/shared key", res.error_message or "")

    def test_dr6_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr6_mlkem512_encaps_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr7_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[10]  # DR7
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR7",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr7_mlkem512_decaps_decrypt.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr7_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP decapsulated shared keys" in note for note in res.corroboration_notes))

    def test_dr7_corrupted_key_fails_validation(self) -> None:
        gate = GATES[10]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR7",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr7_mlkem512_decaps_decrypt.cc",
            dispatches=25,
        )
        # Corrupt 1 shared key in case index 0
        rec["test_buffers"] = _make_dr7_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP decapsulated shared key", res.error_message or "")

    def test_dr7_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr7_mlkem512_decaps_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr8_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[11]  # DR8
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR8",
            expected_count=75,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr8_mlkem768_keygen_finalize.cc",
            dispatches=75,
        )
        rec["test_buffers"] = _make_dr8_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 75 official NIST ACVP ML-KEM (512, 768, 1024) shared keys" in note for note in res.corroboration_notes))

    def test_dr8_corrupted_key_fails_validation(self) -> None:
        gate = GATES[11]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR8",
            expected_count=75,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr8_mlkem768_keygen_finalize.cc",
            dispatches=75,
        )
        # Corrupt 1 shared key in case index 0
        rec["test_buffers"] = _make_dr8_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP shared key", res.error_message or "")

    def test_dr8_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr8_mlkem_service as service
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(service.NativeBackendUnavailable) as ctx:
                service.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(service.NativeBackendUnavailable) as ctx:
                service.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr9_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[12]  # DR9
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR9",
            expected_count=122,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr9_fips202_service.cc",
            dispatches=122,
        )
        rec["test_buffers"] = _make_dr9_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 122 official NIST FIPS 202 digests" in note for note in res.corroboration_notes))

    def test_dr9_corrupted_key_fails_validation(self) -> None:
        gate = GATES[12]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR9",
            expected_count=122,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr9_fips202_service.cc",
            dispatches=122,
        )
        # Corrupt 1 digest in case index 0
        rec["test_buffers"] = _make_dr9_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST FIPS 202 digest", res.error_message or "")

    def test_dr9_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr9_fips202_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr10_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[13]  # DR10
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR10",
            expected_count=40,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr10_sealed_lifecycle_service.cc",
            dispatches=40,
        )
        rec["test_buffers"] = _make_dr10_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 40 DR10 lifecycle cases" in note for note in res.corroboration_notes))

    def test_dr10_corrupted_key_fails_validation(self) -> None:
        gate = GATES[13]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR10",
            expected_count=40,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr10_sealed_lifecycle_service.cc",
            dispatches=40,
        )
        # Corrupt 1 status in case index 0
        rec["test_buffers"] = _make_dr10_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against DR10 lifecycle specification", res.error_message or "")

    def test_dr10_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr10_sealed_lifecycle_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))

    def test_dr11_valid_test_buffers_verified_by_parent_oracle(self) -> None:
        gate = GATES[14]  # DR11
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR11",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr11_mldsa44_keygen_finalize.cc",
            dispatches=25,
        )
        rec["test_buffers"] = _make_dr11_test_buffers()
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_SELF_REPORTED_UNVERIFIED)
        self.assertTrue(any("Parent independent oracle verified all 25 official NIST ACVP ML-DSA-44 key pairs" in note for note in res.corroboration_notes))

    def test_dr11_corrupted_key_fails_validation(self) -> None:
        gate = GATES[14]
        now = datetime.now(timezone.utc)
        rec = _make_valid_record(
            gate_id="DR11",
            expected_count=25,
            artifact_rel="phoenix_sdr_dsp/pqc/kernels/dr11_mldsa44_keygen_finalize.cc",
            dispatches=25,
        )
        # Corrupt 1 key in case index 0
        rec["test_buffers"] = _make_dr11_test_buffers(corrupt_index=0)
        stdout = _wrap_record_in_stdout(rec)
        res = parse_gate_output(
            gate, stdout, "", 0, 0.5,
            parent_start_time=now - timedelta(seconds=2),
            parent_end_time=now + timedelta(seconds=2),
            execution_nonce="test_nonce_0123456789abcdef",
        )
        self.assertFalse(res.success)
        self.assertEqual(res.status, STATUS_FAIL)
        self.assertIn("oracle mismatch against official NIST ACVP ML-DSA-44 key pair", res.error_message or "")

    def test_dr11_module_rejects_emulation_and_xrt_ini_path(self) -> None:
        from phoenix_sdr_dsp.pqc import dr11_mldsa44_keygen_graph as graph
        with mock.patch.dict(os.environ, {"XCL_EMULATION_MODE": "sw_emu"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XCL_EMULATION_MODE='sw_emu'", str(ctx.exception))

        with mock.patch.dict(os.environ, {"XRT_INI_PATH": "C:/fake/xrt.ini"}):
            with self.assertRaises(graph.NativeBackendUnavailable) as ctx:
                graph.check_emulation_and_redirection_excluded()
            self.assertIn("XRT_INI_PATH='C:/fake/xrt.ini'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
