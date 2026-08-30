# SPDX-License-Identifier: Apache-2.0
"""Tests for deterministic agent and evidence policy enforcement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agent_integrity import REPO_ROOT as LIB_ROOT
from agent_integrity import scan_python_file, validate_evidence


class PythonPolicyTests(unittest.TestCase):
    def scan_source(self, filename: str, source: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary:
            path = Path(temporary) / filename
            path.write_text(source, encoding="utf-8")
            relative = path.relative_to(REPO_ROOT)
            with mock.patch("agent_integrity.EXCLUDED_POLICY_PATHS", set()):
                return scan_python_file(relative)

    def test_assert_true_is_blocking(self):
        findings = self.scan_source("ordinary.py", "assert True\n")
        self.assertIn("PY001", {finding.rule for finding in findings})

    def test_host_crypto_import_in_physical_test_is_blocking(self):
        findings = self.scan_source("test_example_silicon.py", "import hashlib\n")
        self.assertIn("HW001", {finding.rule for finding in findings})

    def test_hardcoded_pass_count_is_blocking(self):
        findings = self.scan_source(
            "runner.py", 'print("TOTAL VERIFIED TEST COUNT: 25 / 25 PASS")\n'
        )
        self.assertIn("TEST002", {finding.rule for finding in findings})

    def test_exception_fallback_call_is_blocking(self):
        findings = self.scan_source(
            "test_example_silicon.py",
            "try:\n"
            "    run_device()\n"
            "except RuntimeError:\n"
            "    run_host_reference()\n",
        )
        self.assertIn("HW002", {finding.rule for finding in findings})


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
            errors = validate_evidence(manifest, root / "manifest.json", check_files=True)
            self.assertTrue(any("escapes" in error for error in errors))


class RepositoryLocationTests(unittest.TestCase):
    def test_library_uses_repository_root(self):
        self.assertEqual(LIB_ROOT, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
