"""Host-only static checks for release-maintenance materials."""

from __future__ import annotations

import hashlib
import json
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
    def test_project_license_metadata_and_file_exception_are_consistent(self) -> None:
        license_text = (REPO / "LICENSE").read_text(encoding="utf-8")
        notice = (REPO / "NOTICE").read_text(encoding="utf-8")
        citation = (REPO / "CITATION.cff").read_text(encoding="utf-8")
        zenodo = json.loads((REPO / ".zenodo.json").read_text(encoding="utf-8"))
        toolchain = TOOLCHAIN.read_text(encoding="utf-8")
        third_party = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        provenance = (REPO / "THIRD_PARTY_PROVENANCE.md").read_text(encoding="utf-8")
        nist_notice = (REPO / "LICENSES" / "NIST-ACVP-NOTICE.txt").read_text(
            encoding="utf-8"
        )
        history = (REPO / "LICENSE_HISTORY.md").read_text(encoding="utf-8")
        contributing = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
        mit_text = (REPO / "LICENSES" / "MIT.txt").read_text(encoding="utf-8")
        kpke = (REPO / "tests" / "m32_mlkem" / "kpke_kernel.cc").read_text(
            encoding="utf-8"
        )

        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0", license_text)
        self.assertIn("Copyright 2026 Midhat Nashar", notice)
        self.assertIn("license: Apache-2.0", citation)
        self.assertIn('version: "0.1.0-rc.4"', citation)
        self.assertIn("A public research repository", citation)
        self.assertEqual(zenodo["version"], "0.1.0-rc.4")
        self.assertEqual(zenodo["license"], "Apache-2.0")
        self.assertEqual(zenodo["access_right"], "open")
        self.assertIn("license: Apache-2.0", toolchain)
        self.assertIn("LICENSES/MIT.txt", third_party)
        self.assertIn("THIRD_PARTY_PROVENANCE.md", third_party)
        self.assertIn(
            "975de31eb83d87039ec88934fdc47d8c312b892d",
            provenance,
        )
        self.assertIn("Comparison anchor only", provenance)
        self.assertIn(
            "c490a3249d01a59de62e007261b5a4c6088d3a98c3979b165c6e0bc5fc7eb935",
            provenance,
        )
        self.assertIn("keep intact this entire notice", nist_notice)
        self.assertIn("Permissions already granted", history)
        self.assertIn("submitted under the repository's", contributing)
        self.assertIn("Apache License 2.0", contributing)
        self.assertIn("immutable upstream URL and revision", contributing)
        self.assertTrue(mit_text.startswith("MIT License"))
        self.assertTrue(kpke.startswith("// SPDX-License-Identifier: MIT"))

    def test_provenance_manifest_matches_local_files(self) -> None:
        provenance = (REPO / "THIRD_PARTY_PROVENANCE.md").read_text(encoding="utf-8")
        rows = re.findall(
            r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|",
            provenance,
            flags=re.MULTILINE,
        )
        self.assertGreaterEqual(len(rows), 26)
        for relative_path, expected_sha256 in rows:
            with self.subTest(path=relative_path):
                path = REPO / relative_path
                self.assertTrue(path.is_file())
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected_sha256,
                )

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
        self.assertIn("19 / 19 GATES PASS", readiness)
        self.assertIn("736 / 736 TEST CASES", readiness)
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
        self.assertIn("100% device-resident", readiness)
        self.assertIn('archive_release: "2.21.75"', toolchain)
        self.assertIn('runtime_version: "2.21.0"', toolchain)
        self.assertNotIn('verified_version: "2.21.0"', toolchain)


if __name__ == "__main__":
    unittest.main()
