# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import unittest
import run_all_silicon_tests as runner

class CanonicalSiliconRunnerBehaviorTests(unittest.TestCase):
    def test_gate_count_and_case_total(self) -> None:
        self.assertEqual(len(runner.GATES), 19)
        self.assertEqual(runner.GATES[0].gate_id, 'DR0')
        self.assertEqual(runner.GATES[-1].gate_id, 'DR15')
        self.assertEqual(sum(gate.expected_total for gate in runner.GATES), 736)

if __name__ == '__main__':
    unittest.main()
