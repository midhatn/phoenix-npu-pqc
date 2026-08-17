"""Off-hardware DR2c exact and fail-closed tests using compiled production C++."""

from __future__ import annotations

import _ctypes
import ctypes
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from phoenix_sdr_dsp.pqc import dr2c_mlkem512_keygen_row_abi as abi
from phoenix_sdr_dsp.pqc import dr2c_mlkem512_keygen_row_graph as graph
from tests.pqc_device_resident.dr2c_reference import keygen_row_reference

KERNELS = REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    rho: bytes
    sigma: bytes
    row_index: int
    request_id: int


def _seed(base: int, case: int) -> bytes:
    return bytes((base + 19 * case + 29 * lane + case * lane) & 0xFF for lane in range(32))


PRE_SILICON_CORPUS = tuple(
    [
        CorpusCase(f"base-row-{row}", bytes(range(32)), bytes(range(32, 64)), row, 0xD2C00000 + row)
        for row in range(2)
    ]
    + [
        CorpusCase(f"varied-{case:02d}", _seed(0x15, case), _seed(0xA3, case), case % 2, 0xD2C10000 + case)
        for case in range(8)
    ]
    + [
        CorpusCase("alternating-row-1", bytes(0 if i % 2 else 255 for i in range(32)), bytes(255 if i % 2 else 0 for i in range(32)), 1, 0xD2C20000),
    ]
)
assert len(PRE_SILICON_CORPUS) == 11


class DR2cReferenceTests(unittest.TestCase):
    def test_independent_fips203_row_has_canonical_shape(self) -> None:
        row = keygen_row_reference(bytes(range(32)), bytes(range(32, 64)), 0)
        self.assertEqual(len(row), 256)
        self.assertTrue(all(0 <= value < 3329 for value in row))
        self.assertEqual(row[:8], (1270, 2185, 1487, 2494, 1388, 1734, 3030, 1976))


class DR2cAbiTests(unittest.TestCase):
    def test_exact_descriptor_layout_and_seed_packing(self) -> None:
        self.assertEqual(abi.build_descriptor(1, 0x78563412), bytes((1, 0x23, 0x52, 0, 1, 3, 5, 0, 0x12, 0x34, 0x56, 0x78, 0, 0, 0, 0)))
        self.assertEqual(abi.pack_seeds(bytes(range(32)), bytes(range(32, 64))), bytes(range(64)))

    def test_bad_public_inputs_fail_before_native_load(self) -> None:
        original = graph._load_iron
        graph._load_iron = lambda: (_ for _ in ()).throw(AssertionError("IRON loaded"))
        try:
            with self.assertRaises(abi.Dr2cAbiError): graph.run_mlkem512_keygen_row(b"x" * 31, b"y" * 32, 0, 0)
            with self.assertRaises(abi.Dr2cAbiError): graph.run_mlkem512_keygen_row(b"x" * 32, b"y" * 31, 0, 0)
            with self.assertRaises(abi.Dr2cAbiError): graph.run_mlkem512_keygen_row(b"x" * 32, b"y" * 32, 2, 0)
            with self.assertRaises(TypeError): graph.run_mlkem512_keygen_row(b"x" * 32, b"y" * 32, True, 0)
        finally:
            graph._load_iron = original

    def test_sentinel_and_fixed_zero_errors_fail_closed(self) -> None:
        with self.assertRaises(abi.Dr2cAbiError): abi.parse_result(abi.result_sentinel(), 0, 3)
        error = bytearray(abi.RESULT_BYTES)
        struct.pack_into("<IIIHBB", error, 0, abi.RESULT_MAGIC, 3, abi.STATUS_BAD_TOKEN, 0, 0, 0)
        with self.assertRaises(abi.Dr2cOperationError): abi.parse_result(error, 0, 3)
        struct.pack_into("<h", error, abi.RESULT_HEADER_BYTES, 1)
        with self.assertRaises(abi.Dr2cAbiError): abi.parse_result(error, 0, 3)


@unittest.skipUnless(shutil.which("g++"), "requires g++ host compiler")
class DR2cProductionKernelHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="dr2c-kernel-test-")
        library = Path(cls._directory.name) / "dr2c_kernels.so"
        subprocess.run(["g++", "-std=c++17", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I", str(KERNELS), str(KERNELS / "dr2c_mlkem512_keygen_row_expand.cc"), str(KERNELS / "dr2c_mlkem512_keygen_row_accumulate.cc"), "-o", str(library)], check=True, capture_output=True, encoding="utf-8")
        cls.library = ctypes.CDLL(str(library))
        cls.seeds_type, cls.descriptor_type = ctypes.c_uint8 * abi.SEEDS_BYTES, ctypes.c_uint8 * abi.DESCRIPTOR_BYTES
        cls.token_type, cls.result_type = ctypes.c_uint8 * abi.INTERNAL_TOKEN_BYTES, ctypes.c_uint8 * abi.RESULT_BYTES

    @classmethod
    def tearDownClass(cls) -> None:
        handle = cls.library._handle
        del cls.library
        if sys.platform == "win32": _ctypes.FreeLibrary(handle)
        else: _ctypes.dlclose(handle)
        cls._directory.cleanup()

    def _run(self, case: CorpusCase, descriptor: bytes | None = None, token_mutator=None) -> tuple[bytes, bytes]:
        token, result = self.token_type(), self.result_type()
        self.library.dr2c_keygen_row_expand(self.seeds_type.from_buffer_copy(abi.pack_seeds(case.rho, case.sigma)), self.descriptor_type.from_buffer_copy(descriptor or abi.build_descriptor(case.row_index, case.request_id)), token)
        raw_token = bytearray(token)
        if token_mutator: token_mutator(raw_token)
        self.library.dr2c_keygen_row_accumulate(self.token_type.from_buffer_copy(raw_token), result)
        return raw_token, bytes(result)

    def test_full_compiled_production_corpus_matches_independent_fips_reference(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                token, raw = self._run(case)
                self.assertNotEqual(token[abi.RESULT_HEADER_BYTES:], b"\x00" * (abi.INTERNAL_TOKEN_BYTES - abi.RESULT_HEADER_BYTES))
                self.assertEqual(abi.parse_result(raw, case.row_index, case.request_id), list(keygen_row_reference(case.rho, case.sigma, case.row_index)))

    def test_repeated_requests_reset_all_worker_state(self) -> None:
        for case in (PRE_SILICON_CORPUS[0], PRE_SILICON_CORPUS[6], PRE_SILICON_CORPUS[-1], PRE_SILICON_CORPUS[0]):
            with self.subTest(case=case.label):
                _, raw = self._run(case)
                self.assertEqual(abi.parse_result(raw, case.row_index, case.request_id), list(keygen_row_reference(case.rho, case.sigma, case.row_index)))

    def test_bad_descriptor_and_corrupted_private_token_have_zero_payload(self) -> None:
        case = PRE_SILICON_CORPUS[0]
        descriptor = bytearray(abi.build_descriptor(case.row_index, case.request_id)); descriptor[5] = 2
        for label, descriptor_arg, mutator in (("descriptor", bytes(descriptor), None), ("row-reserved", None, lambda token: token.__setitem__(9, 1)), ("coefficient", None, lambda token: struct.pack_into("<H", token, 16, 3329)), ("status", None, lambda token: struct.pack_into("<I", token, 4, 99))):
            with self.subTest(label=label):
                _, raw = self._run(case, descriptor_arg, mutator)
                with self.assertRaises(abi.Dr2cOperationError): abi.parse_result(raw, case.row_index, case.request_id)
                self.assertEqual(raw[abi.RESULT_HEADER_BYTES:], b"\x00" * 512)


if __name__ == "__main__":
    unittest.main()
