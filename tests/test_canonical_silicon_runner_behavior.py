"""Host-only behavioral tests for canonical native-runner parsing.

The runner is imported as plain stdlib code and its subprocess entry points are
never called. These tests prove acceptance of the exact five native gate
records and fail-closed rejection of host/reference/unavailable/generic output
without compiling or dispatching an AIE program.
"""

from __future__ import annotations

import contextlib
import io
import unittest

import run_all_silicon_tests as runner


def exact_output(gate: runner.NativeGate) -> str:
    return (
        f"Backend: {gate.backend_label}\n"
        f"TOTAL {gate.expected_total}/{gate.expected_total} PASS"
    )


class CanonicalSiliconRunnerBehaviorTests(unittest.TestCase):
    def test_exact_five_gate_order_labels_and_case_total(self) -> None:
        self.assertEqual(
            tuple(gate.gate_id for gate in runner.GATES),
            ("DR0", "DR1", "DR2a", "DR2b", "DR2c"),
        )
        self.assertEqual(
            tuple(gate.backend_label for gate in runner.GATES),
            (
                "m33-dr0:silicon",
                "dr1-mldsa44-expanda-rejntt:silicon",
                "dr2a-mlkem512-samplentt:silicon",
                "dr2b-mlkem512-noise-ntt:silicon",
                "dr2c-mlkem512-keygen-row:silicon",
            ),
        )
        self.assertEqual(
            tuple(gate.expected_total for gate in runner.GATES), (24, 33, 13, 13, 11)
        )
        self.assertEqual(sum(gate.expected_total for gate in runner.GATES), 94)

    def test_each_gate_accepts_only_its_exact_backend_and_total(self) -> None:
        for gate in runner.GATES:
            with self.subTest(gate=gate.gate_id):
                self.assertEqual(
                    runner.validate_gate_output(gate, exact_output(gate)), (True, "")
                )

    def test_parser_fails_closed_for_nonphysical_or_ambiguous_output(self) -> None:
        gate = runner.GATES[1]
        invalid = (
            "Backend: dr1-mldsa44-expanda-rejntt:unavailable\nTOTAL 33/33 PASS",
            "Backend: dr1-mldsa44-expanda-rejntt:reference\nTOTAL 33/33 PASS",
            "Backend: dr1-mldsa44-expanda-rejntt:silicon\nTOTAL 32/33 PASS",
            "Backend: generic backend\nTOTAL 33/33 PASS",
            exact_output(gate) + "\nBackend: dr1-mldsa44-expanda-rejntt:silicon",
            exact_output(gate) + "\nTOTAL 33/33 PASS",
            "TOTAL 33/33 PASS",
        )
        for output in invalid:
            with self.subTest(output=output):
                accepted, reason = runner.validate_gate_output(gate, output)
                self.assertFalse(accepted)
                self.assertTrue(reason)

    def test_list_mode_only_prints_the_native_plan(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(runner.main(["--list"]), 0)
        text = output.getvalue()
        self.assertIn("DR0", text)
        self.assertIn("DR1", text)
        self.assertIn("DR2a", text)
        self.assertIn("DR2b", text)
        self.assertIn("DR2c", text)
        self.assertIn("no preflight, no compilation, and no dispatch", text)
        self.assertNotIn("DR2d:", text)

    def test_evidence_name_is_timestamped_json(self) -> None:
        path = runner.evidence_path(runner.REPO_ROOT / "release-evidence")
        self.assertEqual(path.parent, runner.REPO_ROOT / "release-evidence")
        self.assertRegex(path.name, r"^canonical-silicon-\d{8}T\d{6}Z-\d+\.json$")


if __name__ == "__main__":
    unittest.main()
