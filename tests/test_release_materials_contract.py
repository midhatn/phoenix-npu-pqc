"""Host-only static checks for release-maintenance materials."""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "validate_clean_clone.ps1"
EVIDENCE = REPO / "docs" / "pqc_dr2_evidence_20260818"
MANIFEST = EVIDENCE / "SHA256SUMS"


class ReleaseMaterialsContractTests(unittest.TestCase):
    def test_clean_clone_script_has_no_hardware_dispatch_path(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8-sig")
        self.assertEqual(source.count("{"), source.count("}"))
        self.assertIn("[switch]$InstallHostDependencies", source)
        self.assertNotIn("RunSilicon", source)
        self.assertIn("numpy==$requiredNumpyVersion", source)
        self.assertIn('"2.5.2"', source)
        self.assertIn("Re-run with -InstallHostDependencies", source)
        self.assertIn("Hardware access: disabled", source)
        self.assertIn("Test-Sha256Manifest", source)
        self.assertIn("run_all_pqc_tests.py", source)

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
        self.assertIn("-InstallHostDependencies", checklist)
        self.assertRegex(checklist, r"no hardware-dispatch\s+switch")


if __name__ == "__main__":
    unittest.main()
