"""Static contracts for the narrow, terminal-only DR1 production graph."""

from __future__ import annotations

import ast
import inspect
import re
import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr1_abi as abi
from phoenix_sdr_dsp.pqc import dr1_mldsa44_rejntt_graph as graph

REPO = Path(__file__).resolve().parents[1]
KERNELS = REPO / "phoenix_sdr_dsp" / "pqc" / "kernels"
DESIGN = REPO / "docs" / "PQC_DR1_DESIGN.md"
PENDING = REPO / "docs" / "PQC_DR1_SILICON_VALIDATION_PENDING.md"
CANONICAL_RUNNER = REPO / "run_all_silicon_tests.py"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


class DR1DeviceResidencyContractTests(unittest.TestCase):
    def test_fixed_public_abi(self) -> None:
        self.assertEqual((abi.RHO_BYTES, abi.DESCRIPTOR_BYTES, abi.XOF_BLOCK_BYTES, abi.RESULT_BYTES), (32, 16, 180, 1040))
        self.assertEqual((abi.ABI_VERSION, abi.OPCODE_EXPANDA_REJNTT, abi.PARAMETER_MLDSA44, abi.BLOCK_CAP), (1, 0x11, 0x44, 8))
        self.assertEqual((abi.N, abi.Q, abi.RESULT_MAGIC), (256, 8_380_417, 0x44523152))
        self.assertEqual(graph.BACKEND_LABEL, "dr1-mldsa44-expanda-rejntt:silicon")

    def test_exact_two_host_ingress_one_internal_and_one_terminal_fifo(self) -> None:
        source = inspect.getsource(graph)
        self.assertNotIn("from __future__ import annotations", source)
        self.assertEqual(source.count("ObjectFifo("), 4)
        self.assertEqual(source.count("ExternalFunction("), 2)
        for name in ("dr1_rho", "dr1_descriptor", "dr1_xof_block", "dr1_result"):
            self.assertIn(f'name="{name}"', source)
        self.assertIn("of_xof_block.prod()", source)
        self.assertIn("of_xof_block.cons()", source)
        self.assertNotIn("in_ctrl", source)
        self.assertEqual(source.count('source_file=str(kernel_path / "dr1_shake128_service.cc")'), 1)
        self.assertEqual(source.count('source_file=str(kernel_path / "dr1_mldsa44_rejntt.cc")'), 1)
        self.assertIn('"dr1_shake128_emit_next"', source)
        self.assertIn('"dr1_rejntt_consume_next"', source)
        self.assertNotIn("emit_block_", source)
        self.assertNotIn("consume_block_", source)

    def test_runtime_has_two_fills_and_one_terminal_drain(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        sequence = _function(tree, "sequence")
        calls = [statement.value for statement in sequence.body if isinstance(statement, ast.Expr)]
        self.assertEqual([call.func.attr for call in calls], ["fill", "fill", "drain"])
        self.assertEqual([call.func.value.id for call in calls], ["rho_prod", "descriptor_prod", "result_cons"])

    def test_only_terminal_result_calls_to_cpu(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        transfers = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "to"]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].func.value.id, "result_t")
        self.assertEqual(transfers[0].args[0].value, "cpu")

    def test_host_validates_before_native_loading_and_never_uses_a_reference(self) -> None:
        source = inspect.getsource(graph.run_mldsa44_expanda_rejntt)
        self.assertLess(source.index("abi.validate_request"), source.index("_load_iron()"))
        self.assertIn("abi.result_sentinel()", source)
        self.assertIn("abi.parse_result", source)
        self.assertNotIn("hashlib", source)
        self.assertNotIn("expanda_rejntt_reference", source)

    def test_production_sources_have_no_test_tree_dependency(self) -> None:
        sources = "\n".join(path.read_text(encoding="utf-8") for path in (REPO / "phoenix_sdr_dsp" / "pqc").rglob("*" ) if path.is_file() and path.suffix in {".py", ".cc", ".hpp"})
        self.assertNotIn("tests/", sources)
        self.assertNotIn("../tests", sources)
        self.assertNotIn("tests.", sources)

    def test_kernel_contracts_cover_incremental_shake_and_fixed_drain(self) -> None:
        permutation = (KERNELS / "dr1_keccak_f1600.hpp").read_text(encoding="utf-8")
        keccak = (KERNELS / "dr1_shake128_service.cc").read_text(encoding="utf-8")
        sampler = (KERNELS / "dr1_mldsa44_rejntt.cc").read_text(encoding="utf-8")
        self.assertIn("__attribute__((noinline)) static void keccak_f1600", permutation)
        self.assertIn("DR1_AIE_DISABLE_LOOP_UNROLL", permutation)
        self.assertIn("dr1_keccak_f1600.hpp", keccak)
        self.assertIn("__attribute__((noinline)) static void emit_next", keccak)
        self.assertIn("DR1_AIE_DISABLE_LOOP_UNROLL", keccak)
        self.assertIn("rho[32]", keccak)
        self.assertIn("g_service.seed[32] = descriptor[4]", keccak)
        self.assertIn("g_service.seed[33] = descriptor[5]", keccak)
        self.assertIn("void dr1_shake128_emit_next", keccak)
        self.assertEqual(re.findall(r"\bvoid\s+(dr1_shake128_emit_\w+)\s*\(", keccak), ["dr1_shake128_emit_next"])
        self.assertNotIn("DR1_EMIT", keccak)
        self.assertIn("clear_bytes(&g_service", keccak)
        self.assertIn("& 0x7fffffU", sampler)
        self.assertIn("z < kQ", sampler)
        self.assertIn("g_sampler.accepted < kN", sampler)
        self.assertIn("kLimitExceeded", sampler)
        self.assertIn("__attribute__((noinline)) static void consume_next", sampler)
        self.assertIn("void dr1_rejntt_consume_next", sampler)
        self.assertEqual(re.findall(r"\bvoid\s+(dr1_rejntt_consume_\w+)\s*\(", sampler), ["dr1_rejntt_consume_next"])
        self.assertNotIn("DR1_CONSUME", sampler)
        self.assertIn("DR1_SAMPLER_DISABLE_LOOP_UNROLL", sampler)
        self.assertIn("clear_bytes(&g_sampler", sampler)

    def test_v3_keccak_lfsr_repair_contract_for_v2_lane_zero_mismatch(self) -> None:
        permutation = (KERNELS / "dr1_keccak_f1600.hpp").read_text(encoding="utf-8")
        keccak = (KERNELS / "dr1_shake128_service.cc").read_text(encoding="utf-8")
        pending = PENDING.read_text(encoding="utf-8")
        # v2 executed on Phoenix but disagreed at coefficient 0.  Keep this
        # source-level guard specific: no read-only round table may return.
        self.assertNotIn("round_constants", permutation)
        self.assertNotIn("static const uint64_t", permutation)
        self.assertIn("static inline int lfsr86540", permutation)
        self.assertIn("uint8_t lfsr = 0x01", permutation)
        self.assertIn("reinterpret_cast<uint64_t *>(state)", permutation)
        self.assertIn("r_off", permutation)
        self.assertIn("alignas(8) uint8_t state[200]", keccak)
        self.assertIn("keccak_f1600(g_service.shake.state)", keccak)
        self.assertIn("v2", pending)
        self.assertIn("lane 0", pending)
        self.assertIn("v3", pending)

    def test_one_kernel_call_is_looped_exactly_eight_times_per_worker(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        keccak_body = _function(tree, "keccak_body")
        sampler_body = _function(tree, "sampler_body")
        keccak_source = ast.unparse(keccak_body)
        sampler_source = ast.unparse(sampler_body)
        self.assertEqual(keccak_source.count("range(abi.BLOCK_CAP)"), 1)
        self.assertEqual(sampler_source.count("range(abi.BLOCK_CAP)"), 1)
        self.assertIn("emit_next(rho, descriptor, xof_block)", keccak_source)
        self.assertIn("consume_next(xof_block, result)", sampler_source)
        self.assertLess(sampler_source.index("result = of_result.acquire(1)"), sampler_source.index("for _ in range(abi.BLOCK_CAP)"))
        self.assertLess(sampler_source.index("for _ in range(abi.BLOCK_CAP)"), sampler_source.index("of_result.release(1)"))

    def test_docs_require_compiler_size_evidence_and_name_static_state_linkage_risk(self) -> None:
        design = DESIGN.read_text(encoding="utf-8")
        pending = PENDING.read_text(encoding="utf-8")
        self.assertIn("16 KiB", design)
        self.assertIn("compiler-reported program size", design)
        self.assertIn("ExternalFunction", pending)
        self.assertIn("g_service", pending)
        self.assertIn("g_sampler", pending)
        self.assertIn("v1 IRON link incident", pending)

    def test_physical_record_is_exact_and_canonical_runner_is_unchanged(self) -> None:
        record = PENDING.read_text(encoding="utf-8")
        runner = CANONICAL_RUNNER.read_text(encoding="utf-8")
        self.assertIn("v3 PHYSICAL PASS for the narrow DR1 milestone", record)
        self.assertIn("TOTAL 33/33 PASS", record)
        self.assertIn("8,448 exact coefficient comparisons", record)
        self.assertIn("PQC_DR1_MLDSA44_v3_physical_corpus_20260817.log", record)
        self.assertIn("85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E", record)
        self.assertIn("PQC_DR0_DR1_complete_host_zero_skip_20260817.log", record)
        self.assertIn("2621EF2E4130003895A9DA46042CEAA232D9C11AA5D24A25D0800978283B9568", record)
        self.assertIn("`56 passed`, no skips", record)
        self.assertIn("| `(0,2)` | `dr1_shake128_emit_next`, called eight times | 9,152 B | 6,608 B | 272 B", record)
        self.assertIn("| `(0,3)` | `dr1_rejntt_consume_next`, called eight times | 5,468 B | 3,328 B | 1,040 B", record)
        self.assertIn("malformed descriptors", record)
        self.assertIn("no claim of complete FIPS 204 device residency", record)
        self.assertNotIn("DR1_MLDSA44_EXPANDA_REJNTT", runner)


if __name__ == "__main__":
    unittest.main()
