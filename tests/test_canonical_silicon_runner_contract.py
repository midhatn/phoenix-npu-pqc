"""Host-only static proof of the canonical physical runner's contract.

These checks are deliberately static (AST plus literal text inspection) and
import-free with respect to the MLIR-AIE runtime. Nothing here compiles an AIE
program, opens an NPU device, or dispatches hardware, so the suite is safe in
CI and on any developer host.

What is proved:

* ``run_all_silicon_tests.py`` declares exactly five native gates, in the order
  DR0 -> DR1 -> DR2a -> DR2b -> DR2c.
* Each gate is bound to its exact ``*_silicon.py`` / DR0 gate script, its exact
  ``Backend: <label>:silicon`` string, and its exact expected case total; the
  totals sum to 94.
* The runner has no host forwarder: it never invokes ``run_all_pqc_tests.py``,
  and it rejects unavailable / skip / reference / fallback / diagnostic output.
* DR2d is excluded from the dispatch sequence.
* The extensionless ``install`` launcher delegates to ``install.py`` and, for a
  default full install, hands off to the canonical physical runner.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANONICAL_RUNNER = REPO / "run_all_silicon_tests.py"
HOST_PREFLIGHT_RUNNER = REPO / "run_all_pqc_tests.py"
INSTALL_LAUNCHER = REPO / "install"
INSTALL_IMPLEMENTATION = REPO / "install.py"
GATE_DIRECTORY = REPO / "tests" / "pqc_device_resident"

EXPECTED_GATES: tuple[tuple[str, str, str, int], ...] = (
    ("DR0", "test_m33_product_dr0.py", "m33-dr0:silicon", 24),
    (
        "DR1",
        "test_dr1_mldsa44_rejntt_silicon.py",
        "dr1-mldsa44-expanda-rejntt:silicon",
        33,
    ),
    (
        "DR2a",
        "test_dr2a_mlkem512_samplentt_silicon.py",
        "dr2a-mlkem512-samplentt:silicon",
        13,
    ),
    (
        "DR2b",
        "test_dr2b_mlkem512_noise_ntt_silicon.py",
        "dr2b-mlkem512-noise-ntt:silicon",
        13,
    ),
    (
        "DR2c",
        "test_dr2c_mlkem512_keygen_row_silicon.py",
        "dr2c-mlkem512-keygen-row:silicon",
        11,
    ),
)
EXPECTED_CASE_TOTAL = 94
REQUIRED_REJECTED_MARKERS = (
    "unavailable",
    "fallback",
    "diagnostic-only",
    "generic-only",
    "skip",
    "host-safe",
)


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assignment(module: ast.Module, name: str) -> ast.expr:
    for node in module.body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name and node.value:
                return node.value
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    raise AssertionError(f"module-level assignment {name!r} was not found")


def _gate_calls(module: ast.Module) -> list[dict[str, object]]:
    gates_node = _assignment(module, "GATES")
    assert isinstance(gates_node, ast.Tuple), "GATES must be a literal tuple"
    gates: list[dict[str, object]] = []
    for element in gates_node.elts:
        assert isinstance(element, ast.Call), "each gate must be a NativeGate(...) call"
        func = element.func
        assert isinstance(func, ast.Name) and func.id == "NativeGate", (
            "gates must be constructed with NativeGate"
        )
        assert not element.args, "NativeGate must be constructed with keywords only"
        fields: dict[str, object] = {}
        for keyword in element.keywords:
            assert keyword.arg is not None
            if isinstance(keyword.value, ast.Constant):
                fields[keyword.arg] = keyword.value.value
            elif isinstance(keyword.value, ast.BinOp) and isinstance(
                keyword.value.right, ast.Constant
            ):
                # TESTS_DIR / "<script>.py"
                fields[keyword.arg] = keyword.value.right.value
            else:
                fields[keyword.arg] = None
        gates.append(fields)
    return gates


class CanonicalSiliconRunnerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CANONICAL_RUNNER.read_text(encoding="utf-8")
        self.module = _module(CANONICAL_RUNNER)

    def test_five_native_gates_in_exact_order_with_exact_expectations(self) -> None:
        gates = _gate_calls(self.module)
        self.assertEqual(len(gates), 5)
        for gate, (gate_id, script, backend, total) in zip(
            gates, EXPECTED_GATES, strict=True
        ):
            self.assertEqual(gate["gate_id"], gate_id)
            self.assertEqual(gate["script"], script)
            self.assertEqual(gate["backend_label"], backend)
            self.assertEqual(gate["expected_total"], total)
            self.assertIsInstance(gate["timeout_seconds"], int)
            self.assertGreater(gate["timeout_seconds"], 0)
            self.assertTrue(
                (GATE_DIRECTORY / str(script)).is_file(),
                msg=f"gate script is missing: {script}",
            )
        self.assertEqual(
            sum(int(gate["expected_total"]) for gate in gates), EXPECTED_CASE_TOTAL
        )

    def test_declared_order_and_totals_are_self_checked_in_source(self) -> None:
        order = _assignment(self.module, "EXPECTED_GATE_ORDER")
        self.assertIsInstance(order, ast.Tuple)
        assert isinstance(order, ast.Tuple)
        self.assertEqual(
            [
                element.value
                for element in order.elts
                if isinstance(element, ast.Constant)
            ],
            [gate_id for gate_id, _, _, _ in EXPECTED_GATES],
        )
        self.assertEqual(_assignment(self.module, "EXPECTED_GATE_COUNT").value, 5)
        self.assertEqual(
            _assignment(self.module, "EXPECTED_CASE_TOTAL").value, EXPECTED_CASE_TOTAL
        )
        # The runner asserts its own invariants at import time.
        self.assertIn(
            "assert tuple(gate.gate_id for gate in GATES) == EXPECTED_GATE_ORDER",
            self.source,
        )
        self.assertIn(
            "assert sum(gate.expected_total for gate in GATES) == EXPECTED_CASE_TOTAL",
            self.source,
        )

    def test_runner_has_no_host_forwarder(self) -> None:
        # The host preflight runner may only be named in prose, never invoked.
        for forbidden in (
            'HOST_PREFLIGHT_RUNNER = "run_all_pqc_tests.py"\nsubprocess',
            'run_all_pqc_tests.py"]',
            "'run_all_pqc_tests.py'",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertNotIn("HOST_SAFE_TESTS", self.source)
        for node in ast.walk(self.module):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.strip() == "run_all_pqc_tests.py"
            ):
                self.fail("canonical runner must not reference the host runner path")
        # Gates are dispatched as subprocesses of the running interpreter only.
        self.assertIn("[sys.executable, str(gate.script)]", self.source)

    def test_runner_rejects_non_physical_output(self) -> None:
        markers = _assignment(self.module, "REJECTED_MARKERS")
        self.assertIsInstance(markers, ast.Tuple)
        assert isinstance(markers, ast.Tuple)
        values = {
            element.value
            for element in markers.elts
            if isinstance(element, ast.Constant)
        }
        for marker in REQUIRED_REJECTED_MARKERS:
            self.assertIn(marker, values)
        self.assertIn("expected exactly one", self.source)
        self.assertIn(
            "TOTAL {gate.expected_total}/{gate.expected_total} PASS", self.source
        )
        self.assertIn("preflight_results = preflight()", self.source)
        self.assertIn("stdout=subprocess.PIPE", self.source)
        self.assertIn("stderr=subprocess.STDOUT", self.source)

    def test_dr2d_is_never_dispatched(self) -> None:
        gates = _gate_calls(self.module)
        for gate in gates:
            self.assertNotIn("dr2d", str(gate["gate_id"]).lower())
            self.assertNotIn("dr2d", str(gate["script"]).lower())
            self.assertNotIn("dr2d", str(gate["backend_label"]).lower())
        self.assertNotIn("dr2d-mlkem512-kpke-keygen:silicon", self.source)
        self.assertIn("not dispatched", self.source)

    def test_default_mode_is_physical_dispatch_and_is_disclosed(self) -> None:
        self.assertIn("PHYSICAL COMPILATION AND DISPATCH", self.source)
        self.assertIn("--preflight-only", self.source)
        self.assertIn("--list", self.source)
        self.assertIn("physically", self.source)
        self.assertIn("NOT complete ML-KEM or ML-DSA", self.source)
        self.assertIn("ensure_ironenv_interpreter", self.source)

    def test_host_preflight_runner_disclaims_silicon_status(self) -> None:
        preflight = HOST_PREFLIGHT_RUNNER.read_text(encoding="utf-8")
        self.assertIn("HOST PREFLIGHT ONLY", preflight)
        self.assertIn("not silicon validation", preflight)
        self.assertIn("run_all_silicon_tests.py", preflight)
        self.assertIn("HOST_SAFE_TESTS", preflight)
        self.assertNotIn('_silicon.py",', preflight)

    def test_default_installer_hands_off_to_the_canonical_runner(self) -> None:
        launcher = INSTALL_LAUNCHER.read_text(encoding="utf-8")
        installer = INSTALL_IMPLEMENTATION.read_text(encoding="utf-8")
        self.assertIn(
            'CANONICAL_PHYSICAL_RUNNER = "run_all_silicon_tests.py"', launcher
        )
        self.assertIn('INSTALL_IMPLEMENTATION = "install.py"', launcher)
        self.assertIn('HANDOFF_OPTION = "--run-tests"', launcher)
        self.assertIn("forwarded.append(HANDOFF_OPTION)", launcher)
        self.assertIn(
            'CANONICAL_PHYSICAL_RUNNER = "run_all_silicon_tests.py"', installer
        )
        self.assertIn("repo_root / CANONICAL_PHYSICAL_RUNNER", installer)
        self.assertIn("if args.run_tests:", installer)
        # Maintenance modes must not trigger the physical handoff.
        launcher_module = _module(INSTALL_LAUNCHER)
        maintenance = _assignment(launcher_module, "MAINTENANCE_OPTIONS")
        self.assertIn("--check-only", ast.dump(maintenance))
        self.assertIn("--download-only", ast.dump(maintenance))
        self.assertIn("--self-test", ast.dump(maintenance))

    def test_launcher_argv_construction_is_deterministic(self) -> None:
        namespace: dict[str, object] = {}
        exec(  # noqa: S102 - static launcher source, executed without __main__
            compile(
                INSTALL_LAUNCHER.read_text(encoding="utf-8"),
                str(INSTALL_LAUNCHER),
                "exec",
            ),
            namespace,
        )
        build = namespace["build_install_argv"]
        self.assertEqual(build([]), ["--run-tests"])
        self.assertEqual(build(["--force"]), ["--force", "--run-tests"])
        self.assertEqual(build(["--check-only"]), ["--check-only"])
        self.assertEqual(build(["--download-only"]), ["--download-only"])
        self.assertEqual(build(["--self-test"]), ["--self-test"])
        self.assertEqual(build(["--no-tests"]), [])
        self.assertEqual(build(["--run-tests"]), ["--run-tests"])

    def test_this_contract_suite_never_dispatches_hardware(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        module = _module(Path(__file__))
        imported: set[str] = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported, {"__future__", "ast", "unittest", "pathlib"})
        for forbidden in ("subprocess", "pyxrt", "aie", "run_gate", "main("):
            self.assertNotIn(f"import {forbidden}", source)


if __name__ == "__main__":
    unittest.main()
