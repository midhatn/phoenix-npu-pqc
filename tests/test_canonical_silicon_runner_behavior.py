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


if __name__ == "__main__":
    unittest.main()
