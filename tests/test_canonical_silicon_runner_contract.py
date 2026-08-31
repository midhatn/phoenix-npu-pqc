# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import ast
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[1]
CANONICAL_RUNNER = REPO / 'run_all_silicon_tests.py'
RESIDENT_RUNNER = REPO / 'tests' / 'pqc_device_resident' / 'test_all_silicon_gates.py'
HOST_PREFLIGHT_RUNNER = REPO / 'run_all_pqc_tests.py'
INSTALL_LAUNCHER = REPO / 'install'
INSTALL_IMPLEMENTATION = REPO / 'install.py'
GATE_DIRECTORY = REPO / 'tests' / 'pqc_device_resident'

EXPECTED_GATES = (
    ('DR0', 'test_m33_product_dr0.py', 'm33-dr0:silicon', 24),
    ('DR1', 'test_dr1_mldsa44_rejntt_silicon.py', 'dr1-mldsa44-expanda-rejntt:silicon', 33),
    ('DR2a', 'test_dr2a_mlkem512_samplentt_silicon.py', 'dr2a-mlkem512-samplentt:silicon', 13),
    ('DR2b', 'test_dr2b_mlkem512_noise_ntt_silicon.py', 'dr2b-mlkem512-noise-ntt:silicon', 13),
    ('DR2c', 'test_dr2c_mlkem512_keygen_row_silicon.py', 'dr2c-mlkem512-keygen-row:silicon', 11),
    ('DR2d', 'test_dr2d_mlkem512_kpke_keygen_silicon.py', 'dr2d-mlkem512-kpke-keygen:silicon', 25),
    ('DR3', 'test_dr3_mlkem512_kpke_encrypt_silicon.py', 'dr3-mlkem512-kpke-encrypt:silicon', 25),
    ('DR4', 'test_dr4_mlkem512_kpke_decrypt_silicon.py', 'dr4-mlkem512-kpke-decrypt:silicon', 25),
    ('DR5', 'test_dr5_mlkem512_keygen_silicon.py', 'dr5-mlkem512-keygen:silicon', 25),
    ('DR6', 'test_dr6_mlkem512_encaps_silicon.py', 'dr6-mlkem512-encaps:silicon', 25),
    ('DR7', 'test_dr7_mlkem512_decaps_silicon.py', 'dr7-mlkem512-decaps:silicon', 25),
    ('DR8', 'test_dr8_mlkem_unified_silicon.py', 'dr8-mlkem-unified:silicon', 75),
    ('DR9', 'test_dr9_fips202_silicon.py', 'dr9-fips202:silicon', 122),
    ('DR10', 'test_dr10_sealed_lifecycle_silicon.py', 'dr10-sealed-lifecycle:silicon', 40),
    ('DR11', 'test_dr11_mldsa44_keygen_silicon.py', 'dr11-mldsa44-keygen:silicon', 25),
    ('DR12', 'test_dr12_mldsa44_sign_silicon.py', 'dr12-mldsa44-sign:silicon', 30),
    ('DR13', 'test_dr13_mldsa44_verify_silicon.py', 'dr13-mldsa44-verify:silicon', 30),
    ('DR14', 'test_dr14_mldsa65_silicon.py', 'dr14-mldsa65:silicon', 85),
    ('DR15', 'test_dr15_mldsa87_silicon.py', 'dr15-mldsa87:silicon', 85),
)
EXPECTED_CASE_TOTAL = 736

EXPECTED_EXTENSION_GATES = (
    ('DR16', 'test_dr16_etsi_qkd014_silicon.py', 'dr16-etsi014:silicon', 25),
    ('DR17', 'test_dr17_mldsa_qkd_auth_silicon.py', 'dr17-mldsa-auth:silicon', 25),
    ('DR18', 'test_dr18_dual_key_combiner_silicon.py', 'dr18-dual-combiner:silicon', 25),
    ('DR19', 'test_dr19_hybrid_session_silicon.py', 'dr19-hybrid-session:silicon', 25),
    ('DR27', 'test_dr27_qrng_reservoir_silicon.py', 'dr27-qrng-reservoir:silicon', 21),
)
EXPECTED_EXTENSION_CASE_TOTAL = 121

EXPECTED_REJECTED_MARKERS = (
    "unavailable",
    "fallback",
    "diagnostic-only",
    "no silicon",
    "simulat",
    "emulat",
    ":reference",
    "reference backend",
    "host backend",
    "host-safe",
    "skip",
    "generic-only",
    "generic backend",
)


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


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
    raise AssertionError(f'assignment {name} not found')


def _gate_calls(module: ast.Module, tuple_name: str = 'GATES') -> list[dict[str, object]]:
    gates_node = _assignment(module, tuple_name)
    assert isinstance(gates_node, ast.Tuple)
    gates = []
    for element in gates_node.elts:
        assert isinstance(element, ast.Call)
        fields = {}
        for keyword in element.keywords:
            if isinstance(keyword.value, ast.Constant):
                fields[keyword.arg] = keyword.value.value
            elif isinstance(keyword.value, ast.BinOp) and isinstance(keyword.value.right, ast.Constant):
                fields[keyword.arg] = keyword.value.right.value
            else:
                fields[keyword.arg] = None
        gates.append(fields)
    return gates


class CanonicalSiliconRunnerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _module(CANONICAL_RUNNER)

    def test_runner_exists(self) -> None:
        self.assertTrue(CANONICAL_RUNNER.is_file())

    def test_resident_runner_exists(self) -> None:
        self.assertTrue(RESIDENT_RUNNER.is_file())

    def test_gate_count_and_order(self) -> None:
        gates = _gate_calls(self.module, 'GATES')
        self.assertEqual(len(gates), len(EXPECTED_GATES))
        for actual, (exp_id, exp_script, exp_label, exp_total) in zip(gates, EXPECTED_GATES):
            self.assertEqual(actual['gate_id'], exp_id)
            self.assertEqual(actual['script'], exp_script)
            self.assertEqual(actual['backend_label'], exp_label)
            self.assertEqual(actual['expected_total'], exp_total)

    def test_expected_case_total(self) -> None:
        total = sum(t for _, _, _, t in EXPECTED_GATES)
        self.assertEqual(total, EXPECTED_CASE_TOTAL)

    def test_extension_gates_count_and_order(self) -> None:
        ext_gates = _gate_calls(self.module, 'EXTENSION_GATES')
        self.assertEqual(len(ext_gates), len(EXPECTED_EXTENSION_GATES))
        for actual, (exp_id, exp_script, exp_label, exp_total) in zip(ext_gates, EXPECTED_EXTENSION_GATES):
            self.assertEqual(actual['gate_id'], exp_id)
            self.assertEqual(actual['script'], exp_script)
            self.assertEqual(actual['backend_label'], exp_label)
            self.assertEqual(actual['expected_total'], exp_total)

    def test_extension_expected_case_total(self) -> None:
        total = sum(t for _, _, _, t in EXPECTED_EXTENSION_GATES)
        self.assertEqual(total, EXPECTED_EXTENSION_CASE_TOTAL)

    def test_gate_scripts_exist_in_tree(self) -> None:
        for _, script_name, _, _ in EXPECTED_GATES:
            self.assertTrue((GATE_DIRECTORY / script_name).is_file(), f'missing: {script_name}')

    def test_extension_gate_scripts_exist_in_tree(self) -> None:
        for _, script_name, _, _ in EXPECTED_EXTENSION_GATES:
            self.assertTrue((GATE_DIRECTORY / script_name).is_file(), f'missing extension: {script_name}')

    def test_rejected_markers_contract(self) -> None:
        rejected_node = _assignment(self.module, 'REJECTED_MARKERS')
        assert isinstance(rejected_node, ast.Tuple)
        markers = tuple(
            elt.value for elt in rejected_node.elts if isinstance(elt, ast.Constant)
        )
        self.assertEqual(markers, EXPECTED_REJECTED_MARKERS)

    def test_result_marker_constants(self) -> None:
        start_marker = _assignment(self.module, 'RESULT_START_MARKER')
        assert isinstance(start_marker, ast.Constant)
        self.assertEqual(start_marker.value, "<<<PQC_SILICON_GATE_RESULT_V1>>>")

        end_marker = _assignment(self.module, 'RESULT_END_MARKER')
        assert isinstance(end_marker, ast.Constant)
        self.assertEqual(end_marker.value, "<<<END_PQC_SILICON_GATE_RESULT_V1>>>")


if __name__ == '__main__':
    unittest.main()
