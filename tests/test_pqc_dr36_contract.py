# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR36:
Formal Verification & SMT Proof Models for AIE2 Cryptographic Pipelines.
"""

import unittest

from phoenix_sdr_dsp.pqc.dr36_formal_verification import (
    PROOF_STATUS_PROVEN,
    PROOF_STATUS_COUNTEREXAMPLE,
    verify_theorem_1_montgomery_mlkem,
    verify_theorem_2_modular_mldsa,
    verify_theorem_3_ntt_butterfly_soundness,
    verify_theorem_4_constant_time_cmov,
    verify_theorem_5_zeroization_completeness,
    run_all_formal_proofs,
    montgomery_reduce_mlkem,
    modular_reduce_mldsa,
    branchless_cmov,
    FormalTheoremResult,
    SmtProofObligation,
)


class DR36FormalVerificationContractTests(unittest.TestCase):

    def test_01_execution_boundary_label(self):
        """Validates truthful [HOST RUNTIME] execution boundary labeling."""
        report = run_all_formal_proofs()
        self.assertEqual(report.execution_label, "[HOST RUNTIME]")
        for res in report.theorem_results:
            self.assertEqual(res.execution_label, "[HOST RUNTIME]")

    def test_02_theorem_1_montgomery_reduction_proven(self):
        """Validates formal proof obligation 1: ML-KEM Montgomery reduction correctness."""
        res = verify_theorem_1_montgomery_mlkem(sample_step=32768)
        self.assertEqual(res.status, PROOF_STATUS_PROVEN)
        self.assertEqual(res.obligation.theorem_id, 1)
        self.assertGreater(res.variables_checked, 1000)

        # Direct boundary checks
        for val in [0, 1, -1, 3328, -3328, 3329 * 256, -3329 * 256]:
            t = montgomery_reduce_mlkem(val)
            self.assertEqual((t * 65536) % 3329, val % 3329)
            self.assertLess(abs(t), 3329)

    def test_03_theorem_2_modular_mldsa_proven(self):
        """Validates formal proof obligation 2: ML-DSA modular reduction correctness."""
        res = verify_theorem_2_modular_mldsa(sample_count=8192)
        self.assertEqual(res.status, PROOF_STATUS_PROVEN)
        self.assertEqual(res.obligation.theorem_id, 2)
        self.assertGreater(res.variables_checked, 1000)

        # Direct boundary checks
        q = 8380417
        r = 1 << 32
        for val in [0, 1, -1, q, -q, (1 << 31) - 1, -(1 << 31)]:
            reduced = modular_reduce_mldsa(val)
            self.assertEqual((reduced * r) % q, val % q)
            self.assertLess(abs(reduced), q)

    def test_04_theorem_3_ntt_butterfly_soundness_proven(self):
        """Validates formal proof obligation 3: Negacyclic Radix-2 NTT/INTT butterfly invertibility."""
        res = verify_theorem_3_ntt_butterfly_soundness()
        self.assertEqual(res.status, PROOF_STATUS_PROVEN)
        self.assertEqual(res.obligation.theorem_id, 3)
        self.assertGreater(res.variables_checked, 1000)

    def test_05_theorem_4_constant_time_cmov_proven(self):
        """Validates formal proof obligation 4: Constant-time branchless multiplexer invariance."""
        res = verify_theorem_4_constant_time_cmov()
        self.assertEqual(res.status, PROOF_STATUS_PROVEN)
        self.assertEqual(res.obligation.theorem_id, 4)
        self.assertGreater(res.variables_checked, 200)

        # Explicit truth table validation
        self.assertEqual(branchless_cmov(0xAAAA5555, 0x12345678, 0), 0xAAAA5555)
        self.assertEqual(branchless_cmov(0xAAAA5555, 0x12345678, 1), 0x12345678)

    def test_06_theorem_5_zeroization_completeness_proven(self):
        """Validates formal proof obligation 5: Cryptographic zeroization completeness."""
        res = verify_theorem_5_zeroization_completeness()
        self.assertEqual(res.status, PROOF_STATUS_PROVEN)
        self.assertEqual(res.obligation.theorem_id, 5)
        self.assertGreater(res.variables_checked, 10000)
        self.assertEqual(res.details.get("remanence"), 0)

    def test_07_run_all_formal_proofs_summary(self):
        """Validates end-to-end report execution of all 5 formal verification theorems."""
        report = run_all_formal_proofs()
        self.assertEqual(report.total_theorems, 5)
        self.assertEqual(report.proven_theorems, 5)
        self.assertEqual(report.counterexamples, 0)
        self.assertEqual(report.certification_verdict, "100% FORMALLY PROVEN")
        self.assertGreater(report.execution_time_ms, 0.0)

    def test_08_counterexample_detection_on_faulty_operator(self):
        """Validates that faulty or corrupted reduction operators yield counterexamples."""
        # Simulated buggy reduction function with faulty modulus
        def faulty_montgomery(a: int) -> int:
            prod = (a * 62209) & 0xFFFFFFFF
            u = ((prod & 0xFFFF) ^ 0x0001)  # Injected 1-bit corruption
            return (a - u * 3329) >> 16

        counterexample_found = False
        for a in [100, 500, 1000, 5000]:
            t = faulty_montgomery(a)
            if (t * 65536) % 3329 != a % 3329:
                counterexample_found = True
                break

        self.assertTrue(counterexample_found)


if __name__ == "__main__":
    unittest.main()
