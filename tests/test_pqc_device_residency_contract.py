"""Static host-only contract checks for the DR0 resident graph.

The point is to make an accidental host-visible intermediate, fallback, or
third Phoenix ingress channel detectable without an NPU toolchain.
"""

from __future__ import annotations

import ast
import inspect
import re
import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc import abi
from phoenix_sdr_dsp.pqc import m33_product_graph as graph

REPO = Path(__file__).resolve().parents[1]
KERNELS = REPO / "phoenix_sdr_dsp" / "pqc" / "kernels"
KERNEL = KERNELS / "m33_product_graph.cc"
ARITHMETIC = KERNELS / "m33a_arithmetic.hpp"
GATE = REPO / "tests" / "pqc_device_resident" / "test_m33_product_dr0.py"
VALIDATION_RECORD = REPO / "docs" / "PQC_DR0_SILICON_VALIDATION_20260817.md"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


class DR0DeviceResidencyContractTests(unittest.TestCase):
    def test_public_abi_is_fixed_two_input_one_output(self) -> None:
        self.assertEqual((abi.N, abi.Q), (256, 8_380_417))
        self.assertEqual(abi.POLYNOMIAL_BYTES, 1024)
        self.assertEqual((abi.INGRESS_COUNT, abi.EGRESS_COUNT), (2, 1))
        self.assertEqual(graph.BACKEND_LABEL, "m33-dr0:silicon")
        self.assertEqual(graph.OUTPUT_SENTINEL, -(1 << 31))
        self.assertIs(graph.run, graph.run_m33_product)

    def test_source_declares_exactly_two_ingress_fifos_and_one_terminal_egress(self) -> None:
        source = inspect.getsource(graph)
        self.assertNotIn("from __future__ import annotations", source)
        self.assertEqual(source.count("ObjectFifo(poly_ty, name="), 3)
        self.assertIn('name="m33_dr0_in_a"', source)
        self.assertIn('name="m33_dr0_in_b"', source)
        self.assertIn('name="m33_dr0_out_c"', source)
        self.assertNotIn("in_ctrl", source)
        self.assertNotIn("packed", source.lower())

    def test_runtime_sequence_has_only_two_fills_and_one_terminal_drain(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        sequence = _function(tree, "sequence")
        calls = [statement.value for statement in sequence.body if isinstance(statement, ast.Expr)]
        self.assertEqual(len(calls), 3)
        methods = [call.func.attr for call in calls if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)]
        self.assertEqual(methods, ["fill", "fill", "drain"])
        self.assertEqual([call.func.value.id for call in calls], ["a_prod", "b_prod", "c_cons"])
        self.assertEqual([call.args[0].id for call in calls], ["a_in", "b_in", "c_out"])

    def test_only_terminal_c_is_transferred_to_host(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        transfers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "to"
        ]
        self.assertEqual(len(transfers), 1)
        self.assertIsInstance(transfers[0].func.value, ast.Name)
        self.assertEqual(transfers[0].func.value.id, "c_t")
        self.assertEqual(len(transfers[0].args), 1)
        self.assertEqual(getattr(transfers[0].args[0], "value", None), "cpu")

    def test_run_path_has_no_reference_fallback_and_checks_terminal_sentinel(self) -> None:
        source = inspect.getsource(graph.run_m33_product)
        self.assertNotIn("reference_negacyclic_product(", source)
        self.assertIn("validate_polynomial(\"a\", a)", source)
        self.assertIn("validate_polynomial(\"b\", b)", source)
        self.assertIn("np.full(N, OUTPUT_SENTINEL", source)
        self.assertIn("any(value == OUTPUT_SENTINEL", source)
        self.assertIn("NativeBackendUnavailable", source)

    def test_production_kernel_has_no_test_tree_dependency(self) -> None:
        production_source = "\n".join(
            source.read_text(encoding="utf-8") for source in KERNELS.glob("*.[ch]*")
        )
        self.assertNotIn("tests/", production_source)
        self.assertNotIn("../tests", production_source)
        kernel = KERNEL.read_text(encoding="utf-8")
        self.assertIn('#include "m33a_arithmetic.hpp"', kernel)
        self.assertNotIn("#include \"../", kernel)

    def test_production_arithmetic_contains_defined_m33a_stages(self) -> None:
        kernel = KERNEL.read_text(encoding="utf-8")
        arithmetic = ARITHMETIC.read_text(encoding="utf-8")
        self.assertIn("constexpr int32_t N          = 256", arithmetic)
        self.assertIn("constexpr int32_t Q          = 8380417", arithmetic)
        self.assertIn("constexpr int32_t QINV       = 58728449", arithmetic)
        self.assertIn("constexpr int32_t F_MONT     = 41978", arithmetic)
        self.assertIn("static const int32_t ZETAS_MONT[256]", arithmetic)
        self.assertIn("static inline int32_t mont_reduce(int64_t a)", arithmetic)
        self.assertIn("static_cast<uint64_t>(low) * static_cast<uint32_t>(QINV)", arithmetic)
        self.assertIn("t_low <= 0x7fffffffU", arithmetic)
        self.assertIn("static void ntt_kernel(int32_t coeffs[N])", arithmetic)
        self.assertIn("static void invntt_kernel(int32_t coeffs[N])", arithmetic)
        self.assertIn("static void basemul_kernel", arithmetic)
        self.assertIn("m33a::ntt_kernel(a_ntt);", kernel)
        self.assertIn("m33a::ntt_kernel(b_ntt);", kernel)
        self.assertIn("m33a::basemul_kernel(product_ntt, a_ntt, b_ntt);", kernel)
        self.assertIn("m33a::invntt_kernel(product_ntt);", kernel)
        self.assertEqual(kernel.count("out_c[i] ="), 1)
        self.assertNotIn("to(\"cpu\")", kernel)

    def test_production_zeta_table_is_complete_and_rederived(self) -> None:
        arithmetic = ARITHMETIC.read_text(encoding="utf-8")
        match = re.search(
            r"ZETAS_MONT\[256\]\s*=\s*\{(?P<entries>.*?)\};",
            arithmetic,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        assert match is not None
        got = [int(value) for value in re.findall(r"-?\d+", match.group("entries"))]
        self.assertEqual(len(got), 256)

        def bit_reverse(value: int) -> int:
            return int(f"{value:08b}"[::-1], 2)

        expected = []
        for index in range(256):
            value = (pow(1753, bit_reverse(index), abi.Q) * (1 << 32)) % abi.Q
            expected.append(value - abi.Q if value > abi.Q // 2 else value)
        expected[0] = 0
        self.assertEqual(got, expected)

    def test_native_gate_is_anchored_and_unavailable_is_not_a_pass(self) -> None:
        source = GATE.read_text(encoding="utf-8")
        title = "PQC DR0 - M33 device-resident polynomial product"
        self.assertIn(f'print("{title}")', source)
        self.assertTrue(title.isascii())
        self.assertNotIn("PQC DR0 —", source)
        self.assertIn("EXPECTED_TOTAL = 24", source)
        self.assertIn("len(DIRECTED_VECTORS) + RANDOM_TRIALS == EXPECTED_TOTAL", source)
        self.assertIn("Backend: m33-dr0:unavailable", source)
        self.assertIn("return 2", source)
        self.assertIn('print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")', source)
        self.assertNotIn("m33-dr0:reference", source)

        record = VALIDATION_RECORD.read_text(encoding="utf-8")
        self.assertIn(
            r"`python tests\pqc_device_resident\test_m33_product_dr0.py`",
            record,
        )
        self.assertIn("`m33-dr0:silicon`", record)
        self.assertIn("4 / 4 PASS", record)
        self.assertIn("20 / 20 PASS", record)
        self.assertIn("`TOTAL 24/24 PASS`", record)
        self.assertIn("| Exit code | 0 |", record)
        self.assertIn("`PQC_DR0_M33_silicon_definitive_20260817.log`", record)
        self.assertIn(
            "`678F1116813F38B1356518FD601060934D8C2D5682C935FFDAD5364E0AD6CA48`",
            record,
        )
        self.assertIn("| Log size | 2410 bytes |", record)
        self.assertIn("| Timestamp | 2026-08-17 19:35:37 +03 |", record)
        self.assertIn("exactly two polynomial ingress transfers", record)
        self.assertIn("terminal polynomial egress (`c`).", record)
        self.assertIn("Complete ML-DSA or complete FIPS 204 conformance.", record)
        self.assertIn("Constant-time execution", record)
        self.assertIn("zeroization", record)
        self.assertIn("CMVP validation/certification", record)


if __name__ == "__main__":
    unittest.main()
