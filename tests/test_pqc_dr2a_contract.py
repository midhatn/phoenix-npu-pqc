"""Static contracts for the narrow terminal-only DR2a production graph."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr2_mlkem512_samplentt_abi as abi
from phoenix_sdr_dsp.pqc import dr2_mlkem512_samplentt_graph as graph

REPO = Path(__file__).resolve().parents[1]
KERNELS = REPO / "phoenix_sdr_dsp" / "pqc" / "kernels"
DESIGN = REPO / "docs" / "PQC_DR2A_DESIGN.md"
PENDING = REPO / "docs" / "PQC_DR2A_SILICON_VALIDATION_PENDING.md"
GATE = REPO / "tests" / "pqc_device_resident" / "test_dr2a_mlkem512_samplentt_silicon.py"
HOST_RUNNER = REPO / "run_all_pqc_tests.py"
COMPATIBILITY_RUNNER = REPO / "run_all_silicon_tests.py"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


class DR2aDeviceResidencyContractTests(unittest.TestCase):
    def test_fixed_public_abi_and_fips203_bound(self) -> None:
        self.assertEqual(
            (abi.RHO_BYTES, abi.DESCRIPTOR_BYTES, abi.XOF_BLOCK_BYTES, abi.RESULT_BYTES),
            (32, 16, 180, 528),
        )
        self.assertEqual(
            (
                abi.ABI_VERSION,
                abi.OPCODE_MLKEM512_SAMPLENTT,
                abi.PARAMETER_MLKEM512,
                abi.BLOCK_CAP,
                abi.FIPS203_CANDIDATE_ITERATION_CAP,
            ),
            (1, 0x21, 0x52, 5, 280),
        )
        self.assertEqual((abi.N, abi.Q, abi.RESULT_MAGIC), (256, 3329, 0x4452324D))
        self.assertEqual(graph.BACKEND_LABEL, "dr2a-mlkem512-samplentt:silicon")

    def test_two_ingress_one_internal_and_one_terminal_fifo_only(self) -> None:
        source = inspect.getsource(graph)
        self.assertEqual(source.count("ObjectFifo("), 4)
        self.assertEqual(source.count("ExternalFunction("), 2)
        for name in ("dr2a_rho", "dr2a_descriptor", "dr2a_xof_block", "dr2a_result"):
            self.assertIn(f'name="{name}"', source)
        self.assertIn("of_xof_block.prod()", source)
        self.assertIn("of_xof_block.cons()", source)
        self.assertNotIn("in_ctrl", source)
        self.assertEqual(
            source.count(
                'source_file=str(kernel_path / "dr2_mlkem512_shake128_service.cc")'
            ),
            1,
        )
        self.assertEqual(
            source.count(
                'source_file=str(kernel_path / "dr2_mlkem512_samplentt.cc")'
            ),
            1,
        )

    def test_runtime_has_two_fills_and_one_terminal_drain(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        sequence = _function(tree, "sequence")
        calls = [
            statement.value
            for statement in sequence.body
            if isinstance(statement, ast.Expr)
        ]
        self.assertEqual([call.func.attr for call in calls], ["fill", "fill", "drain"])
        self.assertEqual(
            [call.func.value.id for call in calls],
            ["rho_prod", "descriptor_prod", "result_cons"],
        )

    def test_only_terminal_result_is_transferred_to_host(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        transfers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "to"
        ]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].func.value.id, "result_t")
        self.assertEqual(transfers[0].args[0].value, "cpu")

    def test_host_validation_precedes_native_loading_without_reference_fallback(self) -> None:
        source = inspect.getsource(graph.run_mlkem512_samplentt)
        self.assertLess(source.index("abi.validate_request"), source.index("_load_iron()"))
        self.assertIn("abi.result_sentinel()", source)
        self.assertIn("abi.parse_result", source)
        self.assertNotIn("hashlib", source)
        self.assertNotIn("samplentt_reference", source)

    def test_production_sources_have_no_test_dependency(self) -> None:
        production = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO / "phoenix_sdr_dsp" / "pqc").rglob("*")
            if path.is_file() and path.suffix in {".py", ".cc", ".hpp"}
        )
        self.assertNotIn("tests/", production)
        self.assertNotIn("../tests", production)
        self.assertNotIn("tests.", production)

    def test_kernel_contracts_cover_continuation_and_complete_or_empty_output(self) -> None:
        producer = (
            KERNELS / "dr2_mlkem512_shake128_service.cc"
        ).read_text(encoding="utf-8")
        sampler = (
            KERNELS / "dr2_mlkem512_samplentt.cc"
        ).read_text(encoding="utf-8")
        self.assertIn('#include "dr1_keccak_f1600.hpp"', producer)
        self.assertIn("constexpr uint32_t kBlockCap = 5", producer)
        self.assertIn("descriptor[4]", producer)
        self.assertIn("descriptor[5]", producer)
        self.assertIn("g_service.shake.cursor == kRate", producer)
        self.assertIn("clear_bytes(&g_service", producer)
        self.assertIn("void dr2a_shake128_emit_next", producer)
        self.assertIn("constexpr uint32_t kBlockCap = 5", sampler)
        self.assertIn("constexpr uint32_t kQ = 3329", sampler)
        self.assertIn("b0 + 256u * (b1 & 0x0fu)", sampler)
        self.assertIn("(b1 >> 4) + 16u * b2", sampler)
        self.assertIn("g_sampler.accepted < kN", sampler)
        self.assertIn("kLimitExceeded", sampler)
        self.assertIn("clear_bytes(&g_sampler", sampler)
        self.assertIn("void dr2a_samplentt_consume_next", sampler)

    def test_workers_loop_exactly_five_times_and_terminal_acquire_wraps_loop(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        keccak_source = ast.unparse(_function(tree, "keccak_body"))
        sampler_source = ast.unparse(_function(tree, "sampler_body"))
        self.assertEqual(keccak_source.count("range(abi.BLOCK_CAP)"), 1)
        self.assertEqual(sampler_source.count("range(abi.BLOCK_CAP)"), 1)
        self.assertIn("emit_next(rho, descriptor, xof_block)", keccak_source)
        self.assertIn("consume_next(xof_block, result)", sampler_source)
        self.assertLess(
            sampler_source.index("result = of_result.acquire(1)"),
            sampler_source.index("for _ in range(abi.BLOCK_CAP)"),
        )
        self.assertLess(
            sampler_source.index("for _ in range(abi.BLOCK_CAP)"),
            sampler_source.index("of_result.release(1)"),
        )

    def test_design_and_physical_record_preserve_scope_and_evidence(self) -> None:
        design = DESIGN.read_text(encoding="utf-8")
        pending = PENDING.read_text(encoding="utf-8")
        self.assertIn("280", design)
        self.assertIn("Appendix B", design)
        self.assertIn("terminal-only", design)
        self.assertIn("not K-PKE KeyGen", design)
        self.assertIn("FIPS 203", design)
        self.assertIn("compiler-reported program size", pending.lower())
        self.assertIn("placement", pending)
        self.assertIn("PHYSICAL PASS", pending)
        self.assertIn("TOTAL 13/13 PASS", pending)
        self.assertIn("c65a53d2c8de882f9a5dc7d9", pending)
        self.assertIn("6,192 B", pending)
        self.assertIn("2,976 B", pending)
        self.assertIn("16 KiB (`0x4000`)", pending)
        self.assertIn("26/26 requests passed", pending)
        self.assertIn("78 tests passed, zero skips, exit code 0", pending)
        self.assertIn("PQC_DR0_DR1_DR2A_complete_host_zero_skip_20260817.log", pending)
        self.assertIn("malformed descriptors or corrupted", pending)
        self.assertIn("run_all_silicon_tests.py", pending)

    def test_native_gate_is_anchored_and_default_runner_is_host_safe(self) -> None:
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("PQC DR2a - ML-KEM-512 bounded SHAKE128 SampleNTT", gate)
        self.assertIn("Backend: dr2a-mlkem512-samplentt:unavailable", gate)
        self.assertIn("return 2", gate)
        self.assertIn('print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")', gate)
        self.assertNotIn("dr2a-mlkem512-samplentt:reference", gate)
        runner = HOST_RUNNER.read_text(encoding="utf-8")
        compatibility = COMPATIBILITY_RUNNER.read_text(encoding="utf-8")
        self.assertIn("HOST_SAFE_TESTS", runner)
        self.assertNotIn("test_dr2a_mlkem512_samplentt_silicon.py", runner)
        self.assertIn("run_all_pqc_tests", compatibility)


if __name__ == "__main__":
    unittest.main()
