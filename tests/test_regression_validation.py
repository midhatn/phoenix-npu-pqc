"""Unit tests for master-runner backend validation policies."""

import unittest

from run_all_silicon_tests import validate_test_output


class ValidationPolicyTests(unittest.TestCase):
    def test_hardware_sentinel(self):
        passed, _ = validate_test_output("work complete\nPASS!", "hardware")
        self.assertTrue(passed)

    def test_hardware_rejects_reference_only_sentinel(self):
        passed, _ = validate_test_output(
            "ALL REFERENCE TESTS PASSED",
            "hardware",
        )
        self.assertFalse(passed)

    def test_reference_policy(self):
        passed, _ = validate_test_output(
            "ALL REFERENCE TESTS PASSED",
            "reference",
        )
        self.assertTrue(passed)

    def test_reference_policy_rejects_generic_pass(self):
        passed, _ = validate_test_output(
            "PASS!\nSUCCESS: calculations completed",
            "reference",
        )
        self.assertFalse(passed)

    def test_m32e_requires_all_silicon_groups(self):
        output = "\n".join(
            (
                "test_silicon_keygen[kg1] PASSED",
                "test_silicon_encaps[en1] PASSED",
                "test_silicon_decaps[de1] PASSED",
                "69 passed",
            )
        )
        passed, _ = validate_test_output(output, "m32e_silicon")
        self.assertTrue(passed)

    def test_m32e_rejects_skipped_silicon(self):
        output = "\n".join(
            (
                "test_silicon_keygen[kg1] SKIPPED",
                "test_silicon_encaps[en1] SKIPPED",
                "test_silicon_decaps[de1] SKIPPED",
                "60 passed, 9 skipped",
            )
        )
        passed, _ = validate_test_output(output, "m32e_silicon")
        self.assertFalse(passed)

    def test_m33_primitive_rejects_reference_backend(self):
        passed, _ = validate_test_output(
            "backend: no silicon runner import path\nTOTAL 420/420 PASS",
            "m33_primitive_silicon",
        )
        self.assertFalse(passed)

    def test_m33_primitive_accepts_silicon_backend(self):
        passed, _ = validate_test_output(
            "backend: silicon\nTOTAL 420/420 PASS",
            "m33_primitive_silicon",
        )
        self.assertTrue(passed)

    def test_m33_primitive_rejects_backend_without_total(self):
        passed, _ = validate_test_output(
            "backend: m33a:silicon\nMODE_NTT 50/50 PASS",
            "m33_primitive_silicon",
        )
        self.assertFalse(passed)

    def test_m33_composer_requires_both_silicon_backends(self):
        passed, _ = validate_test_output(
            "backend: m33a:silicon, m33b:reference\nTOTAL 75/75 PASS",
            "m33_composer_silicon",
        )
        self.assertFalse(passed)

        passed, _ = validate_test_output(
            "backend: m33a:silicon, m33b:silicon\nTOTAL 75/75 PASS",
            "m33_composer_silicon",
        )
        self.assertTrue(passed)

    def test_m33_composer_rejects_backends_without_total(self):
        passed, _ = validate_test_output(
            "backend: m33a:silicon, m33b:silicon\nML-DSA-44 25/25 PASS",
            "m33_composer_silicon",
        )
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
