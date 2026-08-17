"""Host-only contract checks for native-only M33 runner integration.

These tests intentionally do not exercise a numerical ML-DSA fallback or
pretend to execute the NPU.  They check the import/ABI/reporting guardrails
that make an actual Phoenix run distinguishable from a host-only run.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from phoenix_sdr_dsp.silicon import m33a_runner, m33b_runner


REPO = Path(__file__).resolve().parents[1]
M33_DIR = REPO / "tests" / "m33_mldsa"


class NativeM33RunnerContractTests(unittest.TestCase):
    def test_m33a_exports_primitive_and_composer_names(self) -> None:
        self.assertEqual(m33a_runner.BACKEND_LABEL, "m33a:silicon")
        self.assertIs(m33a_runner.run, m33a_runner.run_m33a)

    def test_m33b_exports_primitive_and_composer_names(self) -> None:
        self.assertEqual(m33b_runner.BACKEND_LABEL, "m33b:silicon")
        self.assertIs(m33b_runner.run, m33b_runner.run_m33b)

    def test_invalid_modes_are_rejected_before_any_device_work(self) -> None:
        with self.assertRaises(ValueError):
            m33a_runner.run_m33a(4, [0] * 256)
        with self.assertRaises(ValueError):
            m33b_runner.run_m33b(6, 0, [0] * 256)

    def test_bad_polynomial_lengths_are_rejected_before_any_device_work(self) -> None:
        with self.assertRaises(ValueError):
            m33a_runner.run_m33a(0, [0] * 255)
        with self.assertRaises(ValueError):
            m33b_runner.run_m33b(0, 0, [0] * 257)

    def test_empty_unused_m33a_operand_is_normalized_before_device_work(self) -> None:
        # [] is the legacy spelling emitted by primitive NTT/INTT/REDUCE calls.
        # Validate its normalization without attempting a hardware dispatch.
        self.assertEqual(m33a_runner._checked_poly("in_b", []).tolist(), [0] * 256)

    def test_kernel_packed_entrypoints_fit_two_input_dma_limit(self) -> None:
        ntt_source = (M33_DIR / "dilithium_ntt_kernel.cc").read_text(encoding="utf-8")
        sampler_source = (M33_DIR / "dilithium_sampler_kernel.cc").read_text(
            encoding="utf-8"
        )
        self.assertIn("void dilithium_ntt_packed(int32_t in_a[MAX_COEFFS]", ntt_source)
        self.assertIn("void dilithium_sampler_packed(int32_t in_a[N]", sampler_source)
        self.assertIn("PACKED_LEN = CTRL_LEN + N", m33a_runner.__loader__.get_source(m33a_runner.__name__))
        self.assertIn("PACKED_LEN = CTRL_LEN + N", m33b_runner.__loader__.get_source(m33b_runner.__name__))

    def test_silicon_gates_do_not_return_the_reference_dispatcher(self) -> None:
        for filename in (
            "test_dilithium_ntt_m33a.py",
            "test_dilithium_sampler_m33b.py",
        ):
            source = (M33_DIR / filename).read_text(encoding="utf-8")
            self.assertNotIn("return _ref_dispatch(", source)
            self.assertIn("Backend:", source)

    def test_composer_gates_require_both_native_labels(self) -> None:
        for filename in (
            "test_mldsa_keygen_m33d.py",
            "test_mldsa_sign_m33e.py",
            "test_mldsa_verify_m33e.py",
        ):
            source = (M33_DIR / filename).read_text(encoding="utf-8")
            self.assertIn("m33a:silicon, m33b:silicon", source)
            self.assertNotIn("m33a:reference", source)
            self.assertNotIn("m33b:reference", source)


if __name__ == "__main__":
    unittest.main()
