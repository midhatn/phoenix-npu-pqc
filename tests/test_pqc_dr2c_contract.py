"""Static ABI, residency, and native-only contracts for terminal DR2c."""

from __future__ import annotations

import ast
import inspect
import subprocess
import unittest
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr2c_mlkem512_keygen_row_abi as abi
from phoenix_sdr_dsp.pqc import dr2c_mlkem512_keygen_row_graph as graph

REPO = Path(__file__).resolve().parents[1]
KERNELS = REPO / "phoenix_sdr_dsp" / "pqc" / "kernels"
DESIGN = REPO / "docs" / "PQC_DR2C_DESIGN.md"
PENDING = REPO / "docs" / "PQC_DR2C_SILICON_VALIDATION_PENDING.md"
GATE = REPO / "tests" / "pqc_device_resident" / "test_dr2c_mlkem512_keygen_row_silicon.py"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)


class DR2cDeviceResidencyContractTests(unittest.TestCase):
    def test_fixed_public_and_private_abi(self) -> None:
        self.assertEqual((abi.RHO_BYTES, abi.SIGMA_BYTES, abi.SEEDS_BYTES, abi.DESCRIPTOR_BYTES, abi.INTERNAL_TOKEN_BYTES, abi.RESULT_BYTES), (32, 32, 64, 16, 2576, 528))
        self.assertEqual((abi.ABI_VERSION, abi.OPCODE_MLKEM512_KEYGEN_ROW, abi.PARAMETER_MLKEM512, abi.ETA1, abi.SAMPLE_NTT_BLOCK_CAP), (1, 0x23, 0x52, 3, 5))
        self.assertEqual((abi.N, abi.Q, abi.RESULT_MAGIC, abi.INTERNAL_POLYNOMIALS), (256, 3329, 0x4332524D, 5))
        self.assertEqual(graph.BACKEND_LABEL, "dr2c-mlkem512-keygen-row:silicon")

    def test_two_ingress_fifos_one_private_row_token_and_one_terminal_output(self) -> None:
        source = inspect.getsource(graph)
        self.assertEqual(source.count("ObjectFifo("), 4)
        self.assertEqual(source.count("ExternalFunction("), 2)
        for name in ("dr2c_seeds", "dr2c_descriptor", "dr2c_row_token", "dr2c_result"):
            self.assertIn(f'name="{name}"', source)
        self.assertIn("of_row_token.prod()", source)
        self.assertIn("of_row_token.cons()", source)
        self.assertNotIn("in_ctrl", source)

    def test_runtime_has_two_fills_one_drain_and_only_result_host_transfer(self) -> None:
        tree = ast.parse(inspect.getsource(graph))
        sequence = _function(tree, "sequence")
        calls = [node.value for node in sequence.body if isinstance(node, ast.Expr)]
        self.assertEqual([call.func.attr for call in calls], ["fill", "fill", "drain"])
        transfers = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "to"]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].func.value.id, "result_t")
        self.assertEqual(transfers[0].args[0].value, "cpu")

    def test_validation_precedes_native_loading_and_no_reference_fallback_exists(self) -> None:
        source = inspect.getsource(graph.run_mlkem512_keygen_row)
        self.assertLess(source.index("abi.validate_request"), source.index("_load_iron()"))
        self.assertIn("abi.result_sentinel()", source)
        self.assertIn("abi.parse_result", source)
        self.assertNotIn("hashlib", source)
        self.assertNotIn("keygen_row_reference", source)

    def test_production_sources_do_not_depend_on_tests(self) -> None:
        production = "\n".join(path.read_text(encoding="utf-8") for path in (REPO / "phoenix_sdr_dsp" / "pqc").rglob("*") if path.is_file() and path.suffix in {".py", ".cc", ".hpp"})
        self.assertNotIn("tests/", production)
        self.assertNotIn("../tests", production)
        self.assertNotIn("tests.", production)

    def test_workers_own_all_sampling_and_multiply_intermediates_then_clear_them(self) -> None:
        expand = (KERNELS / "dr2c_mlkem512_keygen_row_expand.cc").read_text(encoding="utf-8")
        accumulate = (KERNELS / "dr2c_mlkem512_keygen_row_accumulate.cc").read_text(encoding="utf-8")
        self.assertIn('#include "dr1_keccak_f1600.hpp"', expand)
        self.assertIn("const uint8_t *rho = seeds", expand)
        self.assertIn("const uint8_t *sigma = seeds + 32", expand)
        self.assertIn("sample_matrix(rho, 0, row", expand)
        self.assertIn("sample_matrix(rho, 1, row", expand)
        self.assertIn("cbd3_ntt(sigma, 0", expand)
        self.assertIn("cbd3_ntt(sigma, 1", expand)
        self.assertIn("row + 2", expand)
        self.assertIn("for (uint32_t stage = 0; stage < 7", expand)
        self.assertIn("clear_bytes(a0", expand)
        self.assertIn("clear_bytes(prf", expand)
        self.assertIn("kBlockCap = 5", expand)
        self.assertIn("multiply_ntts(a0, s0, p0)", accumulate)
        self.assertIn("multiply_ntts(a1, s1, p1)", accumulate)
        self.assertIn("clear_bytes(token, kTokenBytes)", accumulate)
        self.assertIn("kBadToken", accumulate)
        self.assertNotIn("pow(", expand + accumulate)

    def test_physical_record_anchors_native_evidence_and_runner_boundary(self) -> None:
        design, record, gate = (
            DESIGN.read_text(encoding="utf-8"),
            PENDING.read_text(encoding="utf-8"),
            GATE.read_text(encoding="utf-8"),
        )
        for phrase in (
            "terminal-only",
            "not K-PKE KeyGen",
            "SampleNTT",
            "SHAKE256",
            "CBD",
            "MultiplyNTTs",
            "FIPS 203",
        ):
            self.assertIn(phrase, design)
        for phrase in (
            "Status: PHYSICAL PASS for the narrow DR2c milestone",
            "2026-08-17",
            "2026-08-17 21:52:40 +03",
            "dr2c-mlkem512-keygen-row:silicon",
            "TOTAL 11/11 PASS",
            "22/22 aggregate",
            "8a683c16baee47604da595bf",
            "final.xclbin`, 23,320 bytes",
            "main.pdi`, 16,864 bytes",
            "partition_main.json`, 717 bytes",
            "memTopology_main.json`, 399 bytes",
            "1f1acd91-079d-4190-9367-6ecec2c18fe5",
            "pdi_id `0x01`",
            "DPU kernel `0x901`",
            "column width 4 from column 0",
            "elfs_main_core_0_2/elfs_main_core_0_2.elf",
            "12,208 B",
            "8,688 B",
            "elfs_main_core_0_3/elfs_main_core_0_3.elf",
            "8,628 B",
            "5,552 B",
            "0x0020000",
            "0x4000` (16 KiB)",
            "0x7C050",
            "0x7C008",
            "four depth-two",
            "dr2c_row_token` | 2,576",
            "address 49,152, bank 3",
            "address 18,976,",
            "address 35,360, bank 2",
            "address 49,216,",
            "shim `(0,0)` DMA0 → tile `(0,2)` DMA0",
            "tile `(0,3)` DMA0 → shim `(0,0)` DMA0",
            "shim `(0,0)` DMA1 → tile `(0,2)` DMA1",
            "descriptor MM2S0, result S2MM0, and seeds MM2S1",
            "There is no shim allocation or flow for `dr2c_row_token`",
            "14/14 PASS; Ruff PASS; `git diff --check` PASS",
            "not establish complete K-PKE.KeyGen or complete ML-KEM",
            "operations-per-cycle metadata",
        ):
            self.assertIn(phrase, record)
        self.assertIn("Backend: dr2c-mlkem512-keygen-row:unavailable", gate)
        self.assertIn("return 2", gate)
        self.assertNotIn("keygen-row:reference", gate)
        self.assertEqual(
            (REPO / "run_all_silicon_tests.py").read_text(encoding="utf-8"),
            subprocess.run(
                ["git", "show", "HEAD:run_all_silicon_tests.py"],
                cwd=REPO,
                check=True,
                capture_output=True,
                encoding="utf-8",
            ).stdout,
        )


if __name__ == "__main__":
    unittest.main()
