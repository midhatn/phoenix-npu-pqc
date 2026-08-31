# SPDX-License-Identifier: Apache-2.0
"""Master Silicon Validation Suite (Physical Silicon Execution).

For host-only preflight tests without physical hardware, see run_all_pqc_tests.py.

Executes and verifies fail-closed physical gates on AMD Phoenix NPU silicon:
  - NIST FIPS 202: SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 (DR9)
  - NIST FIPS 203: ML-KEM-512, ML-KEM-768, ML-KEM-1024 (DR2d, DR3, DR4, DR5, DR6, DR7, DR8)
  - NIST FIPS 204: ML-DSA-44, ML-DSA-65, ML-DSA-87 (DR11, DR12, DR13, DR14, DR15)
  - Hybrid QKD + PQC Defense-in-Depth: DR16, DR17, DR18, DR19
  - Device-Resident Foundation & Lifecycle: DR0, DR1, DR2a, DR2b, DR2c, DR10

Target Hardware: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1).
All physical gates require machine-readable per-case structured evidence records.

TRUST BOUNDARY:
Child JSON is a claim transport format, not physical evidence. Nonce echo prevents
stale replay but does not prevent a child process from fabricating current-run claims.
Independent physical verification requires trusted out-of-band dispatch observation,
hardware device identity verification, and independent KAT buffer comparison. Every
child-emitted record remains SELF_REPORTED_UNVERIFIED until corroborated by independent
runtime verification. No physical PASS pathway exists in this baseline stage.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent
TESTS_DIR = REPO_ROOT / "tests" / "pqc_device_resident"

RESULT_START_MARKER = "<<<PQC_SILICON_GATE_RESULT_V1>>>"
RESULT_END_MARKER = "<<<END_PQC_SILICON_GATE_RESULT_V1>>>"

STATUS_FAIL = "FAIL"
STATUS_BLOCKED = "BLOCKED"
STATUS_SELF_REPORTED_UNVERIFIED = "SELF_REPORTED_UNVERIFIED"
STATUS_INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_MISSING = "MISSING"

REJECTED_MARKERS: tuple[str, ...] = (
    "unavailable",
    "fallback",
    "diagnostic-only",
    "no silicon",
    "simulat",
    "emulat",
    ":reference",
    "reference backend",
    "host backend",
    "host-safe",
    "skip",
    "generic-only",
    "generic backend",
)

DIAGNOSTIC_REJECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bunavailable\b", re.IGNORECASE),
    re.compile(r"\bfallback\b", re.IGNORECASE),
    re.compile(r"\bdiagnostic-only\b", re.IGNORECASE),
    re.compile(r"\bno silicon\b", re.IGNORECASE),
    re.compile(r"\bsimulat(?:ion|ed|or)?\b", re.IGNORECASE),
    re.compile(r"\bemulat(?:ion|ed|or)?\b", re.IGNORECASE),
    re.compile(r":reference\b", re.IGNORECASE),
    re.compile(r"\breference backend\b", re.IGNORECASE),
    re.compile(r"\bhost backend\b", re.IGNORECASE),
    re.compile(r"\bhost-safe\b", re.IGNORECASE),
    re.compile(r"\bgeneric-only\b", re.IGNORECASE),
    re.compile(r"\bgeneric backend\b", re.IGNORECASE),
)


def get_ironenv_path() -> Path:
    if "IRONENV_DIR" in os.environ:
        return Path(os.environ["IRONENV_DIR"])
    default_tree = REPO_ROOT / "third_party" / "mlir-aie" / "ironenv"
    if (default_tree / "Scripts" / "python.exe").is_file():
        return default_tree
    return Path(r"C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv")


def get_ironenv_python() -> Path:
    ironenv = get_ironenv_path()
    if sys.platform == "win32":
        return ironenv / "Scripts" / "python.exe"
    return ironenv / "bin" / "python"


IRONENV = get_ironenv_path()
IRONENV_PYTHON = get_ironenv_python()


def verify_execution_environment(python_exe: Path | None = None) -> tuple[bool, str]:
    """Verify that the configured physical-silicon execution environment interpreter exists.

    Checks that the configured IRON virtual environment interpreter file exists.
    Rejects emulation/simulation modes (XCL_EMULATION_MODE).
    Does not prove NPU presence, driver status, or dispatch authorization.
    Never silently falls back to generic python.
    """
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        return False, (
            f"Physical silicon execution rejected: XCL_EMULATION_MODE={emulation_mode!r} is set.\n"
            "Hardware ground truth forbids simulation or emulation backends."
        )
    target_python = python_exe or get_ironenv_python()
    if not target_python.is_file():
        return False, (
            f"Configured IRON environment interpreter not found at `{target_python}`.\n"
            "Execution requires the documented IRON environment (third_party/mlir-aie/ironenv).\n"
            "Silent fallback to host generic Python is forbidden under zero-speculation policy."
        )
    return True, f"Configured IRON environment interpreter exists at `{target_python}`."


@dataclass(frozen=True)
class NativeGate:
    """One fail-closed physical gate in the canonical ordered sequence."""

    gate_id: str
    title: str
    script: Path
    backend_label: str
    expected_total: int
    timeout_seconds: int = 1800

    @property
    def relative_script(self) -> Path:
        if self.script.is_absolute():
            try:
                return self.script.relative_to(REPO_ROOT)
            except ValueError:
                return self.script
        return self.script


@dataclass(frozen=True)
class CaseResult:
    """Explicit per-case outcome record."""

    case_id: str
    status: str
    details: str = ""


@dataclass(frozen=True)
class GateExecutionResult:
    """Structured execution outcome for a single native gate."""

    gate: NativeGate
    success: bool
    status: str
    exit_code: int | None
    cases_selected: int
    cases_executed: int
    cases_passed: int
    cases_failed: int
    cases_unverified: int
    cases_skipped: int
    cases_xfailed: int
    case_results: tuple[CaseResult, ...]
    duration_seconds: float
    error_message: str | None = None
    rejected_markers: tuple[tuple[int, str, str], ...] = ()
    machine_readable_record: dict[str, object] | None = None
    corroboration_notes: tuple[str, ...] = ()


GATES: tuple[NativeGate, ...] = (
    NativeGate(
        gate_id="DR0",
        title="Gate 00: DR0 M33 Ring Product",
        script=TESTS_DIR / "test_m33_product_dr0.py",
        backend_label="m33-dr0:silicon",
        expected_total=24,
    ),
    NativeGate(
        gate_id="DR1",
        title="Gate 01: DR1 ML-DSA-44 ExpandA",
        script=TESTS_DIR / "test_dr1_mldsa44_rejntt_silicon.py",
        backend_label="dr1-mldsa44-expanda-rejntt:silicon",
        expected_total=33,
    ),
    NativeGate(
        gate_id="DR2a",
        title="Gate 02: DR2a ML-KEM-512 SampleNTT",
        script=TESTS_DIR / "test_dr2a_mlkem512_samplentt_silicon.py",
        backend_label="dr2a-mlkem512-samplentt:silicon",
        expected_total=13,
    ),
    NativeGate(
        gate_id="DR2b",
        title="Gate 03: DR2b ML-KEM-512 CBD3/NTT",
        script=TESTS_DIR / "test_dr2b_mlkem512_noise_ntt_silicon.py",
        backend_label="dr2b-mlkem512-noise-ntt:silicon",
        expected_total=13,
    ),
    NativeGate(
        gate_id="DR2c",
        title="Gate 04: DR2c ML-KEM-512 KeyGen Row",
        script=TESTS_DIR / "test_dr2c_mlkem512_keygen_row_silicon.py",
        backend_label="dr2c-mlkem512-keygen-row:silicon",
        expected_total=11,
    ),
    NativeGate(
        gate_id="DR2d",
        title="Gate 05: DR2d ML-KEM-512 K-PKE KeyGen",
        script=TESTS_DIR / "test_dr2d_mlkem512_kpke_keygen_silicon.py",
        backend_label="dr2d-mlkem512-kpke-keygen:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR3",
        title="Gate 06: DR3 ML-KEM-512 K-PKE Encrypt",
        script=TESTS_DIR / "test_dr3_mlkem512_kpke_encrypt_silicon.py",
        backend_label="dr3-mlkem512-kpke-encrypt:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR4",
        title="Gate 07: DR4 ML-KEM-512 K-PKE Decrypt",
        script=TESTS_DIR / "test_dr4_mlkem512_kpke_decrypt_silicon.py",
        backend_label="dr4-mlkem512-kpke-decrypt:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR5",
        title="Gate 08: DR5 ML-KEM-512 ML-KEM KeyGen",
        script=TESTS_DIR / "test_dr5_mlkem512_keygen_silicon.py",
        backend_label="dr5-mlkem512-keygen:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR6",
        title="Gate 09: DR6 ML-KEM-512 ML-KEM Encaps",
        script=TESTS_DIR / "test_dr6_mlkem512_encaps_silicon.py",
        backend_label="dr6-mlkem512-encaps:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR7",
        title="Gate 10: DR7 ML-KEM-512 ML-KEM Decaps",
        script=TESTS_DIR / "test_dr7_mlkem512_decaps_silicon.py",
        backend_label="dr7-mlkem512-decaps:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR8",
        title="Gate 11: DR8 ML-KEM-768 & 1024 Expansion",
        script=TESTS_DIR / "test_dr8_mlkem_unified_silicon.py",
        backend_label="dr8-mlkem-unified:silicon",
        expected_total=75,
    ),
    NativeGate(
        gate_id="DR9",
        title="Gate 12: DR9 FIPS 202 SHA-3/SHAKE Service",
        script=TESTS_DIR / "test_dr9_fips202_silicon.py",
        backend_label="dr9-fips202:silicon",
        expected_total=122,
    ),
    NativeGate(
        gate_id="DR10",
        title="Gate 13: DR10 Sealed Lifecycle & Key Sources",
        script=TESTS_DIR / "test_dr10_sealed_lifecycle_silicon.py",
        backend_label="dr10-sealed-lifecycle:silicon",
        expected_total=40,
    ),
    NativeGate(
        gate_id="DR11",
        title="Gate 14: DR11 ML-DSA-44 KeyGen",
        script=TESTS_DIR / "test_dr11_mldsa44_keygen_silicon.py",
        backend_label="dr11-mldsa44-keygen:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR12",
        title="Gate 15: DR12 ML-DSA-44 Sign",
        script=TESTS_DIR / "test_dr12_mldsa44_sign_silicon.py",
        backend_label="dr12-mldsa44-sign:silicon",
        expected_total=30,
    ),
    NativeGate(
        gate_id="DR13",
        title="Gate 16: DR13 ML-DSA-44 Verify",
        script=TESTS_DIR / "test_dr13_mldsa44_verify_silicon.py",
        backend_label="dr13-mldsa44-verify:silicon",
        expected_total=30,
    ),
    NativeGate(
        gate_id="DR14",
        title="Gate 17: DR14 ML-DSA-65 (KeyGen, Sign, Verify)",
        script=TESTS_DIR / "test_dr14_mldsa65_silicon.py",
        backend_label="dr14-mldsa65:silicon",
        expected_total=85,
    ),
    NativeGate(
        gate_id="DR15",
        title="Gate 18: DR15 ML-DSA-87 (KeyGen, Sign, Verify)",
        script=TESTS_DIR / "test_dr15_mldsa87_silicon.py",
        backend_label="dr15-mldsa87:silicon",
        expected_total=85,
    ),
)

EXTENSION_GATES: tuple[NativeGate, ...] = (
    NativeGate(
        gate_id="DR16",
        title="Gate 19: DR16 ETSI GS QKD 014 Sealed Ingress",
        script=TESTS_DIR / "test_dr16_etsi_qkd014_silicon.py",
        backend_label="dr16-etsi014:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR17",
        title="Gate 20: DR17 ML-DSA Asymmetric QKD Control",
        script=TESTS_DIR / "test_dr17_mldsa_qkd_auth_silicon.py",
        backend_label="dr17-mldsa-auth:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR18",
        title="Gate 21: DR18 NIST SP 800-56C Dual Combiner",
        script=TESTS_DIR / "test_dr18_dual_key_combiner_silicon.py",
        backend_label="dr18-dual-combiner:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR19",
        title="Gate 22: DR19 Hybrid QKD-PQC Session Orchestrator",
        script=TESTS_DIR / "test_dr19_hybrid_session_silicon.py",
        backend_label="dr19-hybrid-session:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR27",
        title="Gate 23: DR27 QRNG-OPENAPI & Entropy Reservoir",
        script=TESTS_DIR / "test_dr27_qrng_reservoir_silicon.py",
        backend_label="dr27-qrng-reservoir:silicon",
        expected_total=21,
    ),
)


def scan_diagnostic_markers(text: str) -> list[tuple[int, str, str]]:
    """Scan diagnostic text line-by-line using precise patterns with line numbers."""
    findings: list[tuple[int, str, str]] = []
    for line_num, line in enumerate(text.splitlines(), start=1):
        for pattern in DIAGNOSTIC_REJECTED_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append((line_num, match.group(0), line.strip()))
                break
    return findings


def extract_canonical_framed_record(
    stdout: str,
) -> tuple[dict[str, object] | None, str, str | None]:
    """Extract exactly one canonically framed JSON evidence record.

    Returns (parsed_dict, non_json_diagnostic_text, error_string).
    """
    start_count = stdout.count(RESULT_START_MARKER)
    end_count = stdout.count(RESULT_END_MARKER)

    if start_count == 0 and end_count == 0:
        return None, stdout, "No machine-readable framed evidence record found in stdout (unmigrated text output is non-authoritative)"
    if start_count != 1 or end_count != 1:
        return None, stdout, f"Framing delimiter anomaly: {start_count} start marker(s), {end_count} end marker(s)"

    start_pos = stdout.find(RESULT_START_MARKER)
    end_pos = stdout.find(RESULT_END_MARKER)
    if start_pos >= end_pos:
        return None, stdout, "Framing error: start delimiter occurs after end delimiter"

    block = stdout[start_pos + len(RESULT_START_MARKER):end_pos].strip()
    non_json_text = stdout[:start_pos] + "\n" + stdout[end_pos + len(RESULT_END_MARKER):]

    try:
        parsed = json.loads(block)
        if not isinstance(parsed, dict):
            return None, non_json_text, "Framed evidence block is not a JSON object"
        return parsed, non_json_text, None
    except json.JSONDecodeError as exc:
        return None, non_json_text, f"Malformed JSON in evidence block: {exc}"


def parse_iso_timestamp(val: object) -> tuple[datetime | None, str | None]:
    """Parse an ISO timestamp requiring explicit timezone information."""
    if not isinstance(val, str) or not val.strip():
        return None, "Timestamp must be a non-empty string"
    raw = val.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None, f"Timezone-naive timestamp rejected ({raw!r}); explicit timezone offset is required"
        return dt, None
    except ValueError as exc:
        return None, f"Invalid ISO timestamp format ({raw!r}): {exc}"


def parse_gate_output(
    gate: NativeGate,
    stdout: str,
    stderr: str,
    exit_code: int | None,
    duration_seconds: float,
    parent_start_time: datetime | None = None,
    parent_end_time: datetime | None = None,
    execution_nonce: str | None = None,
    error_message: str | None = None,
    repo_root: Path = REPO_ROOT,
    tolerance_seconds: float = 5.0,
) -> GateExecutionResult:
    """Validate gate execution under the repository zero-speculation policy.

    Every child-emitted record is classified as SELF_REPORTED_UNVERIFIED until
    independent hardware dispatch and KAT output corroboration is implemented.
    There is intentionally no physical PASS status in this baseline stage.
    """
    if error_message or exit_code is None:
        return GateExecutionResult(
            gate=gate,
            success=False,
            status=STATUS_INFRASTRUCTURE_FAILURE if "interpreter" in str(error_message).lower() else STATUS_FAIL,
            exit_code=exit_code,
            cases_selected=gate.expected_total,
            cases_executed=0,
            cases_passed=0,
            cases_failed=gate.expected_total,
            cases_unverified=0,
            cases_skipped=0,
            cases_xfailed=0,
            case_results=(),
            duration_seconds=duration_seconds,
            error_message=error_message or "Execution failed without exit code",
            rejected_markers=(),
            machine_readable_record=None,
            corroboration_notes=(),
        )

    record, non_json_diag, framing_err = extract_canonical_framed_record(stdout)
    rejected_findings = scan_diagnostic_markers(non_json_diag + ("\n" + stderr if stderr else ""))

    if record is None:
        err = framing_err or "No machine-readable framed record"
        if rejected_findings:
            markers_detail = "; ".join(f"line {l}: '{m}' in '{t}'" for l, m, t in rejected_findings)
            err += f"; rejected marker(s) detected: {markers_detail}"
        return GateExecutionResult(
            gate=gate,
            success=False,
            status=STATUS_BLOCKED,
            exit_code=exit_code,
            cases_selected=gate.expected_total,
            cases_executed=0,
            cases_passed=0,
            cases_failed=0,
            cases_unverified=0,
            cases_skipped=0,
            cases_xfailed=0,
            case_results=(),
            duration_seconds=duration_seconds,
            error_message=err,
            rejected_markers=tuple(rejected_findings),
            machine_readable_record=None,
            corroboration_notes=(),
        )

    corroboration_notes: list[str] = []
    failures: list[str] = []

    # 1. Execution Nonce / Session Binding
    if execution_nonce is not None:
        rec_nonce = record.get("execution_nonce")
        if rec_nonce != execution_nonce:
            failures.append(f"execution_nonce mismatch or missing (expected {execution_nonce!r}, got {rec_nonce!r})")
        else:
            corroboration_notes.append("Execution nonce verified and bound to current run.")

    # 2. Schema and Gate Identity
    if record.get("schema_version") != 1:
        failures.append(f"schema_version must equal 1 (got {record.get('schema_version')})")
    if record.get("gate_id") != gate.gate_id:
        failures.append(f"gate_id {record.get('gate_id')!r} != expected {gate.gate_id!r}")
    if record.get("execution_boundary") != "[ON-TILE SILICON]":
        failures.append(f"execution_boundary {record.get('execution_boundary')!r} != '[ON-TILE SILICON]'")
    if record.get("evidence_class") != "BIT_EXACT_PHYSICAL_SILICON":
        failures.append(f"evidence_class {record.get('evidence_class')!r} != 'BIT_EXACT_PHYSICAL_SILICON'")

    # 3. Independent Timestamp Verification (Strict Timezone-Aware)
    child_start, start_err = parse_iso_timestamp(record.get("started_at"))
    if start_err:
        failures.append(f"started_at error: {start_err}")
    child_end, end_err = parse_iso_timestamp(record.get("ended_at") or record.get("completed_at"))
    if end_err:
        failures.append(f"ended_at error: {end_err}")

    if child_start is not None and child_end is not None:
        if child_start > child_end:
            failures.append(f"Timestamp inversion: started_at ({child_start}) > ended_at ({child_end})")
        if parent_start_time is not None and parent_end_time is not None:
            if child_start.timestamp() < parent_start_time.timestamp() - tolerance_seconds:
                failures.append(f"Stale started_at ({child_start}) before parent spawn ({parent_start_time})")
            if child_end.timestamp() > parent_end_time.timestamp() + tolerance_seconds:
                failures.append(f"Future ended_at ({child_end}) after parent completion ({parent_end_time})")
        if not failures:
            corroboration_notes.append("Timestamps parsed and verified within parent-observed execution window.")

    # 4. Source / File Integrity Check
    artifact = record.get("artifact")
    if not isinstance(artifact, dict):
        failures.append("artifact field must be an object")
    else:
        art_rel = artifact.get("path") or artifact.get("name")
        art_claimed_sha = artifact.get("sha256")
        if not isinstance(art_rel, str) or not art_rel.strip():
            failures.append("artifact.path must be a non-empty string")
        elif not isinstance(art_claimed_sha, str) or not re.fullmatch(r"^[0-9a-f]{64}$", art_claimed_sha.lower()):
            failures.append("artifact.sha256 must be a 64-character lowercase hex digest")
        else:
            try:
                art_full = (repo_root / art_rel).resolve()
                repo_full = repo_root.resolve()
                if not art_full.is_relative_to(repo_full):
                    failures.append(f"Artifact path traversal rejected: {art_rel}")
                elif not art_full.is_file():
                    failures.append(f"Artifact file not found on disk: {art_rel}")
                else:
                    recomputed_sha = hashlib.sha256(art_full.read_bytes()).hexdigest().lower()
                    if recomputed_sha != art_claimed_sha.lower():
                        failures.append(
                            f"Artifact SHA-256 mismatch: recomputed {recomputed_sha} != claimed {art_claimed_sha}"
                        )
                    else:
                        corroboration_notes.append(f"Source/file integrity verified: {art_rel} matches disk SHA-256.")
            except Exception as exc:
                failures.append(f"Artifact verification error: {exc}")

    # 5. Device Identity Format Check (Independent probe deferred to DR0-TRACE-DISPATCH)
    device = record.get("device")
    if not isinstance(device, dict):
        failures.append("device field must be an object")
    else:
        for f in ("device_name", "device_id", "driver", "firmware"):
            if not isinstance(device.get(f), str) or not device.get(f):
                failures.append(f"device.{f} must be a non-empty string")

    # 6. Dispatch Claim Format Check
    dispatch = record.get("dispatch")
    if not isinstance(dispatch, dict):
        failures.append("dispatch field must be an object")
    else:
        dispatches = dispatch.get("physical_dispatches")
        if not isinstance(dispatches, int) or isinstance(dispatches, bool) or dispatches < 1:
            failures.append("dispatch.physical_dispatches must be an integer >= 1")
        if dispatch.get("completed") is not True:
            failures.append("dispatch.completed must be true")

    # 7. Declared Counts Validation (Integer, non-boolean, matching)
    decl_selected = record.get("cases_selected")
    if decl_selected is None:
        failures.append("Missing required field: cases_selected")
    elif not isinstance(decl_selected, int) or isinstance(decl_selected, bool):
        failures.append(f"cases_selected must be an integer, got {type(decl_selected).__name__}")
    elif decl_selected != gate.expected_total:
        failures.append(f"cases_selected ({decl_selected}) != expected total ({gate.expected_total})")

    # 8. Explicit Cases Array Verification
    cases = record.get("cases")
    counts = {"passed_claims": 0, "failed_claims": 0, "skipped": 0, "xfailed": 0}
    case_results_list: list[CaseResult] = []

    if not isinstance(cases, list) or not cases:
        failures.append("cases must be a non-empty array")
    else:
        decl_executed = record.get("cases_executed")
        if decl_executed is None:
            failures.append("Missing required field: cases_executed")
        elif not isinstance(decl_executed, int) or isinstance(decl_executed, bool):
            failures.append(f"cases_executed must be an integer, got {type(decl_executed).__name__}")
        elif decl_executed != len(cases):
            failures.append(f"cases_executed ({decl_executed}) != cases length ({len(cases)})")

        if len(cases) != gate.expected_total:
            failures.append(f"cases array length ({len(cases)}) != expected gate total ({gate.expected_total})")

        seen_case_ids: set[str] = set()
        for idx, case in enumerate(cases):
            if not isinstance(case, dict):
                failures.append(f"cases[{idx}] must be an object")
                continue
            cid = case.get("case_id")
            if not isinstance(cid, str) or not cid.strip():
                failures.append(f"cases[{idx}].case_id must be a non-empty string")
                continue
            if cid in seen_case_ids:
                failures.append(f"duplicate case_id {cid!r} at index {idx}")
            seen_case_ids.add(cid)
            st = str(case.get("status", "")).upper()
            case_results_list.append(CaseResult(case_id=cid, status=st, details=str(case.get("details", ""))))
            if st == "PASS":
                counts["passed_claims"] += 1
            elif st in {"SKIP", "SKIPPED"}:
                counts["skipped"] += 1
            elif st in {"XFAIL", "XPASS"}:
                counts["xfailed"] += 1
            else:
                counts["failed_claims"] += 1

        if counts["passed_claims"] != gate.expected_total:
            failures.append(f"passed claims ({counts['passed_claims']}) != expected ({gate.expected_total})")
        if counts["failed_claims"] > 0:
            failures.append(f"{counts['failed_claims']} case(s) reported failure")
        if counts["skipped"] > 0:
            failures.append(f"{counts['skipped']} case(s) skipped")
        if counts["xfailed"] > 0:
            failures.append(f"{counts['xfailed']} case(s) xfailed")

    # 9. Process Exit Code Check
    rec_exit = record.get("exit_code")
    if rec_exit != 0 or exit_code != 0:
        failures.append(f"non-zero exit code (child {exit_code}, record {rec_exit})")

    # 10. Process ID (PID) Validation
    child_pid = record.get("child_pid")
    if child_pid is not None:
        if not isinstance(child_pid, int) or isinstance(child_pid, bool) or child_pid <= 0:
            failures.append(f"child_pid must be a positive integer, got {child_pid!r}")
        else:
            corroboration_notes.append(f"Child process PID verified: {child_pid}")

    # 11. Parent-Side Independent Test Buffers / Oracle Verification (DR0 Scope)
    test_buffers = record.get("test_buffers")
    if test_buffers is not None:
        if not isinstance(test_buffers, list):
            failures.append("test_buffers field must be an array")
        elif len(test_buffers) != gate.expected_total:
            failures.append(f"test_buffers length ({len(test_buffers)}) != expected gate total ({gate.expected_total})")
        else:
            from phoenix_sdr_dsp.pqc import abi
            buffer_mismatches = 0
            for b_idx, buf_entry in enumerate(test_buffers):
                if not isinstance(buf_entry, dict):
                    failures.append(f"test_buffers[{b_idx}] must be an object")
                    continue
                in_a = buf_entry.get("input_a")
                in_b = buf_entry.get("input_b")
                out_c = buf_entry.get("output_c")
                if not isinstance(in_a, list) or not isinstance(in_b, list) or not isinstance(out_c, list):
                    failures.append(f"test_buffers[{b_idx}] input_a, input_b, output_c must be integer lists")
                    continue
                if len(in_a) != abi.N or len(in_b) != abi.N or len(out_c) != abi.N:
                    failures.append(f"test_buffers[{b_idx}] buffer lengths must equal {abi.N}")
                    continue
                try:
                    expected = abi.reference_negacyclic_product(in_a, in_b)
                    if out_c != expected:
                        buffer_mismatches += 1
                        mismatch_lane = next(
                            i for i, (got_val, want_val) in enumerate(zip(out_c, expected)) if got_val != want_val
                        )
                        failures.append(
                            f"test_buffers[{b_idx}] ({buf_entry.get('case_name')}) oracle mismatch at lane {mismatch_lane}: "
                            f"got {out_c[mismatch_lane]}, expected {expected[mismatch_lane]}"
                        )
                except Exception as exc:
                    failures.append(f"test_buffers[{b_idx}] oracle evaluation error: {exc}")
            if buffer_mismatches == 0 and not failures:
                corroboration_notes.append(
                    f"Parent independent oracle verified all {len(test_buffers)} x {abi.N} output coefficients."
                )

    # 12. Emulation and Redirection Mode Check
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        failures.append(f"XCL_EMULATION_MODE={emulation_mode!r} is active in environment")

    # 13. Diagnostic Markers Check
    if rejected_findings:
        markers_detail = "; ".join(f"line {l}: '{m}' in '{t}'" for l, m, t in rejected_findings)
        failures.append(f"rejected marker(s) detected: {markers_detail}")

    has_errors = len(failures) > 0
    if has_errors:
        final_status = STATUS_FAIL
        is_success = False
        err_str = "; ".join(failures)
        cases_unverified = counts["passed_claims"]
        cases_failed = counts["failed_claims"]
    else:
        final_status = STATUS_SELF_REPORTED_UNVERIFIED
        is_success = False
        err_str = (
            "Child record is well-formed but physical hardware dispatch remains "
            "uncorroborated (pending DR0-TRACE-DISPATCH independent runtime verifier)"
        )
        cases_unverified = counts["passed_claims"]
        cases_failed = 0

    executed_total = (
        cases_unverified
        + cases_failed
        + counts["skipped"]
        + counts["xfailed"]
    )
    return GateExecutionResult(
        gate=gate,
        success=is_success,
        status=final_status,
        exit_code=exit_code,
        cases_selected=gate.expected_total,
        cases_executed=executed_total,
        cases_passed=0,  # Strictly 0 for uncorroborated runs
        cases_failed=cases_failed,
        cases_unverified=cases_unverified,
        cases_skipped=counts["skipped"],
        cases_xfailed=counts["xfailed"],
        case_results=tuple(case_results_list),
        duration_seconds=duration_seconds,
        error_message=err_str,
        rejected_markers=tuple(rejected_findings),
        machine_readable_record=record,
        corroboration_notes=tuple(corroboration_notes),
    )


def run_single_gate(
    gate: NativeGate,
    python_exe: str | Path,
    repo_root: Path = REPO_ROOT,
) -> GateExecutionResult:
    """Run one native gate and return independently verified structured execution evidence."""
    full_path = (
        gate.script
        if gate.script.is_absolute()
        else repo_root / gate.script
    )
    if not full_path.is_file():
        return GateExecutionResult(
            gate=gate,
            success=False,
            status=STATUS_MISSING,
            exit_code=None,
            cases_selected=gate.expected_total,
            cases_executed=0,
            cases_passed=0,
            cases_failed=gate.expected_total,
            cases_unverified=0,
            cases_skipped=0,
            cases_xfailed=0,
            case_results=(),
            duration_seconds=0.0,
            error_message=f"Gate script not found: {gate.relative_script}",
            rejected_markers=(),
            machine_readable_record=None,
            corroboration_notes=(),
        )

    execution_nonce = secrets.token_hex(16)
    env = os.environ.copy()
    env["PQC_EXECUTION_NONCE"] = execution_nonce

    t0 = time.time()
    parent_start = datetime.now(timezone.utc)
    try:
        res = subprocess.run(
            [str(python_exe), "-u", str(full_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=gate.timeout_seconds,
            env=env,
        )
        parent_end = datetime.now(timezone.utc)
        dt = time.time() - t0
        return parse_gate_output(
            gate=gate,
            stdout=res.stdout,
            stderr=res.stderr,
            exit_code=res.returncode,
            duration_seconds=dt,
            parent_start_time=parent_start,
            parent_end_time=parent_end,
            execution_nonce=execution_nonce,
            repo_root=repo_root,
        )
    except subprocess.TimeoutExpired as exc:
        parent_end = datetime.now(timezone.utc)
        dt = time.time() - t0
        stdout_str = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr_str = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return GateExecutionResult(
            gate=gate,
            success=False,
            status=STATUS_TIMEOUT,
            exit_code=None,
            cases_selected=gate.expected_total,
            cases_executed=0,
            cases_passed=0,
            cases_failed=gate.expected_total,
            cases_unverified=0,
            cases_skipped=0,
            cases_xfailed=0,
            case_results=(),
            duration_seconds=dt,
            error_message=f"Gate timed out after {gate.timeout_seconds}s",
            rejected_markers=tuple(scan_diagnostic_markers(stdout_str + "\n" + stderr_str)),
            machine_readable_record=None,
            corroboration_notes=(),
        )
    except Exception as exc:
        dt = time.time() - t0
        return GateExecutionResult(
            gate=gate,
            success=False,
            status=STATUS_FAIL,
            exit_code=None,
            cases_selected=gate.expected_total,
            cases_executed=0,
            cases_passed=0,
            cases_failed=gate.expected_total,
            cases_unverified=0,
            cases_skipped=0,
            cases_xfailed=0,
            case_results=(),
            duration_seconds=dt,
            error_message=f"Execution failed: {type(exc).__name__}: {exc}",
            rejected_markers=(),
            machine_readable_record=None,
            corroboration_notes=(),
        )


def execute_suite(
    gates: tuple[NativeGate, ...],
    python_exe: str | Path,
    repo_root: Path = REPO_ROOT,
    verbose: bool = True,
) -> tuple[list[GateExecutionResult], float]:
    """Execute a collection of gates and return per-gate results with elapsed time."""
    start_all = time.time()
    results: list[GateExecutionResult] = []
    for gate in gates:
        result = run_single_gate(
            gate,
            python_exe,
            repo_root,
        )
        results.append(result)
        if verbose:
            if result.success:
                print(
                    f"[+] {gate.title:<52} : PASS ({result.duration_seconds:5.2f}s, "
                    f"{result.cases_passed}/{result.cases_selected} cases)"
                )
            else:
                reason = f", {result.error_message}" if result.error_message else ""
                exit_str = f", exit {result.exit_code}" if result.exit_code is not None else ""
                status_label = result.status
                print(
                    f"[-] {gate.title:<52} : {status_label} "
                    f"({result.duration_seconds:5.2f}s{exit_str}{reason})"
                )
    dt_all = time.time() - start_all
    return results, dt_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Master Silicon Validation Suite")
    parser.add_argument("--list", action="store_true", help="List all registered candidate native gates")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include QKD/QRNG extension gates (24 gates total)",
    )
    args = parser.parse_args()

    active_gates = GATES + EXTENSION_GATES if args.all else GATES

    if args.list:
        total_cases = sum(g.expected_total for g in active_gates)
        print(f"Registered {len(active_gates)} Candidate Native Hardware Gates ({total_cases} total cases):")
        for g in active_gates:
            print(f"  {g.gate_id:<6}: {g.title} ({g.expected_total} cases)")
        return 0

    print("=" * 80)
    print("MASTER SILICON VALIDATION SUITE (PHYSICAL SILICON EXECUTION)")
    print("Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)")
    print(f"Scope: {len(active_gates)} Native Hardware Gates")
    print("=" * 80)

    # Fail closed if the configured physical runtime environment is missing.
    env_ok, env_msg = verify_execution_environment()
    if not env_ok:
        print(f"INFRASTRUCTURE FAILURE: {env_msg}", file=sys.stderr)
        return 1

    python_exe = get_ironenv_python()
    results, dt_all = execute_suite(active_gates, python_exe, REPO_ROOT)

    total_gates = len(active_gates)
    passed_gates = sum(1 for r in results if r.success)
    unverified_gates = sum(1 for r in results if r.status == STATUS_SELF_REPORTED_UNVERIFIED)
    blocked_gates = sum(1 for r in results if r.status == STATUS_BLOCKED)
    failed_gates = total_gates - passed_gates - unverified_gates - blocked_gates

    total_cases_selected = sum(g.expected_total for g in active_gates)
    total_cases_passed = sum(r.cases_passed for r in results)
    total_cases_unverified = sum(r.cases_unverified for r in results)
    total_cases_failed = sum(r.cases_failed for r in results)
    total_cases_blocked = sum(r.cases_selected for r in results if r.status == STATUS_BLOCKED)

    print("=" * 80)
    print(f"MASTER SILICON SUITE RESULT: {passed_gates}/{total_gates} GATES PHYSICALLY VERIFIED ({dt_all:.2f}s)")
    print(f"Gate Status Breakdown: {unverified_gates} unverified, {blocked_gates} blocked, {failed_gates} failed")
    print(
        f"Case Status Breakdown: {total_cases_passed} verified passed, {total_cases_unverified} unverified claims, "
        f"{total_cases_failed} verified case failures, {total_cases_blocked} blocked of {total_cases_selected} selected."
    )
    print("NOTICE: Physical silicon verification is BLOCKED pending trusted dispatch and KAT-output corroboration.")
    print("=" * 80)

    return 0 if (
        failed_gates == 0
        and unverified_gates == 0
        and blocked_gates == 0
        and total_gates > 0
        and total_cases_passed == total_cases_selected
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
