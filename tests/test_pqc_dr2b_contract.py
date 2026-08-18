"""Static residency, ABI, and fail-closed contracts for terminal-only DR2b."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr2b_mlkem512_noise_ntt_abi as abi
from phoenix_sdr_dsp.pqc import dr2b_mlkem512_noise_ntt_graph as graph
from tests.production_dependency_guard import assert_no_test_dependency_imports

REPO = Path(__file__).resolve().parents[1]
KERNELS = REPO / "phoenix_sdr_dsp" / "pqc" / "kernels"
DESIGN = REPO / "docs" / "PQC_DR2B_DESIGN.md"
PENDING = REPO / "docs" / "PQC_DR2B_SILICON_VALIDATION_PENDING.md"
GATE = (
    REPO / "tests" / "pqc_device_resident" / "test_dr2b_mlkem512_noise_ntt_silicon.py"
)


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


class DR2bDeviceResidencyContractTests(unittest.TestCase):
    def test_fixed_public_abi(self) -> None:
        self.assertEqual(
            (
                abi.SIGMA_BYTES,
                abi.DESCRIPTOR_BYTES,
                abi.PRF_BYTES,
                abi.PRF_TOKEN_BYTES,
                abi.RESULT_BYTES,
            ),
            (32, 16, 192, 208, 528),
        )
        self.assertEqual(
            (
                abi.ABI_VERSION,
                abi.OPCODE_MLKEM512_NOISE_NTT,
                abi.PARAMETER_MLKEM512,
                abi.ETA1,
                abi.COUNTER_MIN,
                abi.COUNTER_MAX,
            ),
            (1, 0x22, 0x52, 3, 0, 3),
        )
        self.assertEqual((abi.N, abi.Q, abi.RESULT_MAGIC), (256, 3329, 0x4232524D))
        self.assertEqual(graph.BACKEND_LABEL, "dr2b-mlkem512-noise-ntt:silicon")

    def test_exactly_two_host_ingress_one_internal_token_and_one_terminal_output(
        self,
    ) -> None:
        source = inspect.getsource(graph)
        self.assertEqual(source.count("ObjectFifo("), 4)
        self.assertEqual(source.count("ExternalFunction("), 2)
        for name in ("dr2b_sigma", "dr2b_descriptor", "dr2b_prf_token", "dr2b_result"):
            self.assertIn(f'name="{name}"', source)
        self.assertIn("of_prf_token.prod()", source)
        self.assertIn("of_prf_token.cons()", source)
        self.assertNotIn("in_ctrl", source)

    def test_runtime_has_two_fills_one_drain_and_only_result_host_transfer(
        self,
    ) -> None:
        tree = ast.parse(inspect.getsource(graph))
        sequence = _function(tree, "sequence")
        calls = [node.value for node in sequence.body if isinstance(node, ast.Expr)]
        self.assertEqual([call.func.attr for call in calls], ["fill", "fill", "drain"])
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

    def test_validation_precedes_native_loading_and_no_reference_fallback_exists(
        self,
    ) -> None:
        source = inspect.getsource(graph.run_mlkem512_eta1_noise_ntt)
        self.assertLess(
            source.index("abi.validate_request"), source.index("_load_iron()")
        )
        self.assertIn("abi.result_sentinel()", source)
        self.assertIn("abi.parse_result", source)
        self.assertNotIn("hashlib", source)
        self.assertNotIn("noise_ntt_reference", source)

    def test_production_sources_do_not_depend_on_tests(self) -> None:
        production = tuple(
            path
            for path in (REPO / "phoenix_sdr_dsp" / "pqc").rglob("*.py")
            if path.is_file()
        )
        assert_no_test_dependency_imports(production)

    def test_device_workers_have_strict_prf_cbd_ntt_and_zero_error_contracts(
        self,
    ) -> None:
        producer = (KERNELS / "dr2b_mlkem512_shake256_prf_service.cc").read_text(
            encoding="utf-8"
        )
        consumer = (KERNELS / "dr2b_mlkem512_cbd_ntt.cc").read_text(encoding="utf-8")
        self.assertIn('#include "dr1_keccak_f1600.hpp"', producer)
        self.assertIn("kRate = 136", producer)
        self.assertIn("d[4] <= 3", producer)
        self.assertIn("d[5] == 3", producer)
        self.assertIn("dr2b_shake256_prf_emit", producer)
        self.assertIn("token[12] != 0", consumer)
        self.assertIn("6 * i", consumer)
        self.assertIn("constexpr uint16_t kZetas[128]", consumer)
        self.assertIn("const uint32_t zeta = kZetas[k++]", consumer)
        self.assertNotIn("bit_reverse7(", consumer)
        self.assertNotIn("pow17(", consumer)
        self.assertIn("for (uint32_t stage = 0; stage < 7", consumer)
        self.assertIn("const uint32_t length = 128u >> stage", consumer)
        self.assertNotIn("length >>= 1", consumer)
        self.assertIn("dr2b_cbd3_ntt_consume", consumer)
        self.assertIn("store_le16(result + 12, status == kOk ? kN : 0)", consumer)

    def test_design_and_physical_record_native_gate_and_host_runner_boundary(
        self,
    ) -> None:
        design, pending, gate = (
            DESIGN.read_text(encoding="utf-8"),
            PENDING.read_text(encoding="utf-8"),
            GATE.read_text(encoding="utf-8"),
        )
        for required in (
            "SHAKE256",
            "CBD",
            "NTT",
            "terminal-only",
            "not K-PKE KeyGen",
            "FIPS 203",
        ):
            self.assertIn(required, design)
        self.assertIn("PHYSICAL PASS", pending)
        self.assertIn("TOTAL 13/13 PASS", pending)
        self.assertIn("26/26 requests passed", pending)
        self.assertIn("92 tests passed, zero skips, exit code 0", pending)
        self.assertIn(
            "PQC_DR0_DR1_DR2A_DR2B_complete_host_zero_skip_20260817.log", pending
        )
        self.assertIn("DR2a `99c80ac`; DR2b `8b1bff2`", pending)
        self.assertIn("byte-compared", pending)
        self.assertIn("4311961d4f3a43976aa5a60d", pending)
        self.assertIn("d420b963-9fb7-47c3-9fda-a9a55ae3ed2d", pending)
        self.assertIn("only the terminal NTT result returns to the host", pending)
        self.assertIn("compiler-reported program size", pending.lower())
        self.assertIn("PQC DR2b - ML-KEM-512 SHAKE256 CBD3 NTT", gate)
        self.assertIn("Backend: dr2b-mlkem512-noise-ntt:unavailable", gate)
        self.assertIn("return 2", gate)
        self.assertNotIn("noise-ntt:reference", gate)
        runner = (REPO / "run_all_pqc_tests.py").read_text(encoding="utf-8")
        compatibility = (REPO / "run_all_silicon_tests.py").read_text(encoding="utf-8")
        self.assertIn("HOST_SAFE_TESTS", runner)
        self.assertNotIn("test_dr2b_mlkem512_noise_ntt_silicon.py", runner)
        self.assertIn("run_all_pqc_tests", compatibility)


if __name__ == "__main__":
    unittest.main()
