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


if __name__ == "__main__":
    unittest.main()
