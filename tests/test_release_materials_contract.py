"""Host-only static checks for release-maintenance materials."""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "validate_clean_clone.ps1"
INSTALL = REPO / "install"
INSTALL_IMPLEMENTATION = REPO / "install.py"
EVIDENCE = REPO / "docs" / "pqc_dr2_evidence_20260818"
MANIFEST = EVIDENCE / "SHA256SUMS"
TOOLCHAIN = REPO / "toolchain.yaml"


class ReleaseMaterialsContractTests(unittest.TestCase):
    def test_extensionless_launcher_is_the_primary_native_install_path(self) -> None:
        launcher = INSTALL.read_text(encoding="utf-8")
        installer = INSTALL_IMPLEMENTATION.read_text(encoding="utf-8")
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        setup = (REPO / "docs" / "SETUP_WINDOWS.md").read_text(encoding="utf-8")

        # The launcher must delegate to the maintained native installer and, for
        # a default full install, hand off to the canonical physical runner.
        self.assertIn('INSTALL_IMPLEMENTATION = "install.py"', launcher)
        self.assertIn(
            'CANONICAL_PHYSICAL_RUNNER = "run_all_silicon_tests.py"', launcher
        )
        self.assertIn('HANDOFF_OPTION = "--run-tests"', launcher)
        self.assertIn("with_name(INSTALL_IMPLEMENTATION)", launcher)
        self.assertIn("MAINTENANCE_OPTIONS", launcher)
        self.assertIn("raise SystemExit(main())", launcher)
        for option in ('"--check-only"', '"--download-only"', '"--self-test"'):
            self.assertIn(option, launcher)

        # The native installer must keep its verified pins and disclose the
        # part of the environment that is not hash-locked.
        self.assertIn(
            'CANONICAL_PHYSICAL_RUNNER = "run_all_silicon_tests.py"', installer
        )
        self.assertIn("run_iron_setup", installer)
        self.assertIn("install_vendored_pyxrt", installer)
        self.assertIn("NOT hash-locked", installer)
        self.assertIn("print_integrity_disclosure", installer)
        self.assertIn("No AIE compilation and no hardware", installer)

        self.assertIn("py .\\install", readme)
        self.assertIn("py .\\install", setup)
        self.assertIn("run_all_silicon_tests.py", readme)
        self.assertIn("run_all_silicon_tests.py", setup)

    def test_clean_checkout_script_is_host_only_and_fails_closed_when_dirty(
        self,
    ) -> None:
        source = SCRIPT.read_text(encoding="utf-8-sig")
        self.assertEqual(source.count("{"), source.count("}"))
        self.assertIn("[switch]$InstallHostDependencies", source)
        self.assertNotIn("RunSilicon", source)
        self.assertIn('"install", "--no-tests"', source)
        self.assertIn('"install", "--check-only"', source)
        self.assertIn("Re-run with ", source)
        self.assertIn("-InstallHostDependencies", source)
        self.assertIn("Hardware access: disabled", source)
        self.assertIn("Test-Sha256Manifest", source)
        self.assertIn("run_all_pqc_tests.py", source)
        self.assertIn('"install", "install.py", "run_all_pqc_tests.py"', source)
        # The only canonical-runner invocation permitted here is the
        # non-dispatching plan listing.
        self.assertIn('"run_all_silicon_tests.py", "--list"', source)
        self.assertEqual(source.count("run_all_silicon_tests.py"), 3)
        self.assertIn("is NOT silicon validation", source)
        self.assertIn("does not create a clone", source)
        self.assertIn("staged, unstaged, or untracked", source)
        self.assertGreaterEqual(source.count("--untracked-files=all"), 2)
        self.assertIn("git rev-parse --verify HEAD", source)
        self.assertIn("HEAD changed during audit", source)
        self.assertIn("full checkout clean after audit", source)

    def test_protected_manifest_matches_every_listed_file(self) -> None:
        checked = 0
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
            self.assertIsNotNone(match, msg=line)
            assert match is not None
            expected, relative = match.groups()
            self.assertEqual(
                hashlib.sha256((EVIDENCE / relative).read_bytes()).hexdigest(),
                expected,
                msg=relative,
            )
            checked += 1
        self.assertGreater(checked, 0)

    def test_publication_documents_preserve_dr2_boundaries(self) -> None:
        readiness = (REPO / "docs" / "PUBLICATION_READINESS.md").read_text(
            encoding="utf-8"
        )
        checklist = (REPO / "docs" / "JOURNAL_REPRODUCIBILITY_CHECKLIST.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("DR2b is solved only", readiness)
        self.assertIn("DR2c is solved only", readiness)
        self.assertIn("`TOTAL 0/25 FAIL`, exit 1", readiness)
        self.assertIn("py .\\install", readiness)
        self.assertIn("-InstallHostDependencies", checklist)
        self.assertRegex(checklist, r"no hardware-dispatch\s+switch")

    def test_release_status_requires_new_native_artifacts_and_unambiguous_xrt(
        self,
    ) -> None:
        readiness = (REPO / "docs" / "PUBLICATION_READINESS.md").read_text(
            encoding="utf-8"
        )
        toolchain = TOOLCHAIN.read_text(encoding="utf-8")
        for required in (
            "tests/pqc_device_resident/test_dr1_mldsa44_rejntt_silicon.py",
            "tests/test_canonical_silicon_runner_behavior.py",
            "tests/test_canonical_silicon_runner_contract.py",
        ):
            self.assertIn(required, readiness)
        self.assertRegex(readiness, r"reviewed,\s+tracked release commit")
        self.assertIn('archive_release: "2.21.75"', toolchain)
        self.assertIn('runtime_version: "2.21.0"', toolchain)
        self.assertNotIn('verified_version: "2.21.0"', toolchain)


if __name__ == "__main__":
    unittest.main()
