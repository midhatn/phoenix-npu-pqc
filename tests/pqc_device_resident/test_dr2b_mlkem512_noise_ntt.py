"""Off-hardware exact and fail-closed DR2b tests using compiled production C++."""

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
from phoenix_sdr_dsp.pqc import dr2b_mlkem512_noise_ntt_abi as abi
from phoenix_sdr_dsp.pqc import dr2b_mlkem512_noise_ntt_graph as graph
from tests.pqc_device_resident.dr2b_reference import (
    cbd3_reference,
    noise_ntt_reference,
    prf_eta1_reference,
)

KERNELS = REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    sigma: bytes
    counter: int
    request_id: int


def _sigma(case: int) -> bytes:
    return bytes(
        (0x51 + 31 * case + 17 * lane + case * lane) & 0xFF for lane in range(32)
    )


PRE_SILICON_CORPUS = tuple(
    [
        CorpusCase(
            f"base-counter-{counter}", bytes(range(32)), counter, 0xD2B00000 + counter
        )
        for counter in range(4)
    ]
    + [
        CorpusCase(
            f"varied-{case:02d}", _sigma(case), (case * 3 + 1) % 4, 0xD2B10000 + case
        )
        for case in range(8)
    ]
    + [
        CorpusCase(
            "alternating-00-ff",
            bytes(0 if i % 2 == 0 else 255 for i in range(32)),
            3,
            0xD2B20000,
        )
    ]
)
assert len(PRE_SILICON_CORPUS) == 13


class DR2bReferenceTests(unittest.TestCase):
    def test_direct_fips203_pipeline_has_fixed_sizes_and_canonical_ntt_output(
        self,
    ) -> None:
        prf = prf_eta1_reference(bytes(range(32)), 0)
        self.assertEqual(len(prf), 192)
        self.assertTrue(all(-3 <= value <= 3 for value in cbd3_reference(prf)))
        output = noise_ntt_reference(bytes(range(32)), 0)
        self.assertEqual(len(output), 256)
        self.assertTrue(all(0 <= value < 3329 for value in output))
        self.assertEqual(output[:8], (2600, 580, 1010, 2263, 1327, 2440, 2490, 3240))


class DR2bAbiTests(unittest.TestCase):
    def test_exact_descriptor_layout(self) -> None:
        self.assertEqual(
            abi.build_descriptor(3, 0x78563412),
            bytes((1, 0x22, 0x52, 0, 3, 3, 192, 0, 0x12, 0x34, 0x56, 0x78, 0, 0, 0, 0)),
        )

    def test_malformed_inputs_fail_before_native_load(self) -> None:
        original = graph._load_iron
        graph._load_iron = lambda: (_ for _ in ()).throw(AssertionError("IRON loaded"))
        try:
            with self.assertRaises(abi.Dr2bAbiError):
                graph.run_mlkem512_eta1_noise_ntt(b"x" * 31, 0, 0)
            with self.assertRaises(abi.Dr2bAbiError):
                graph.run_mlkem512_eta1_noise_ntt(b"x" * 32, 4, 0)
            with self.assertRaises(TypeError):
                graph.run_mlkem512_eta1_noise_ntt(b"x" * 32, True, 0)
            with self.assertRaises(abi.Dr2bAbiError):
                graph.run_mlkem512_eta1_noise_ntt(b"x" * 32, 0, 1 << 32)
        finally:
            graph._load_iron = original

    def test_sentinel_and_fixed_zero_errors_fail_closed(self) -> None:
        with self.assertRaises(abi.Dr2bAbiError):
            abi.parse_result(abi.result_sentinel(), 3)
        error = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHBB", error, 0, abi.RESULT_MAGIC, 3, abi.STATUS_BAD_TOKEN, 0, 7, 0
        )
        with self.assertRaises(abi.Dr2bOperationError):
            abi.parse_result(error, 3)
        struct.pack_into("<h", error, abi.RESULT_HEADER_BYTES, 1)
        with self.assertRaises(abi.Dr2bAbiError):
            abi.parse_result(error, 3)


@unittest.skipUnless(shutil.which("g++"), "requires g++ host compiler")
class DR2bProductionKernelHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="dr2b-kernel-test-")
        library = Path(cls._directory.name) / "dr2b_kernels.so"
        subprocess.run(
            [
                "g++",
                "-std=c++17",
                "-shared",
                "-fPIC",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-I",
                str(KERNELS),
                str(KERNELS / "dr2b_mlkem512_shake256_prf_service.cc"),
                str(KERNELS / "dr2b_mlkem512_cbd_ntt.cc"),
                "-o",
                str(library),
            ],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        cls.library = ctypes.CDLL(str(library))
        cls.sigma_type = ctypes.c_uint8 * abi.SIGMA_BYTES
        cls.descriptor_type = ctypes.c_uint8 * abi.DESCRIPTOR_BYTES
        cls.token_type = ctypes.c_uint8 * abi.PRF_TOKEN_BYTES
        cls.result_type = ctypes.c_uint8 * abi.RESULT_BYTES

    @classmethod
    def tearDownClass(cls) -> None:
        handle = cls.library._handle
        del cls.library
        if sys.platform == "win32":
            _ctypes.FreeLibrary(handle)
        else:
            _ctypes.dlclose(handle)
        cls._directory.cleanup()

    def _run(
        self, case: CorpusCase, descriptor: bytes | None = None, token_mutator=None
    ) -> tuple[bytes, bytes]:
        token, result = self.token_type(), self.result_type()
        self.library.dr2b_shake256_prf_emit(
            self.sigma_type.from_buffer_copy(case.sigma),
            self.descriptor_type.from_buffer_copy(
                descriptor or abi.build_descriptor(case.counter, case.request_id)
            ),
            token,
        )
        raw_token = bytearray(token)
        if token_mutator:
            token_mutator(raw_token)
        self.library.dr2b_cbd3_ntt_consume(
            self.token_type.from_buffer_copy(raw_token), result
        )
        return bytes(raw_token), bytes(result)

    def test_full_compiled_production_corpus_matches_independent_fips_reference(
        self,
    ) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                token, raw = self._run(case)
                self.assertEqual(
                    token[16:], prf_eta1_reference(case.sigma, case.counter)
                )
                self.assertEqual(
                    abi.parse_result(raw, case.request_id),
                    list(noise_ntt_reference(case.sigma, case.counter)),
                )

    def test_repeated_requests_reset_all_request_state(self) -> None:
        for case in (
            PRE_SILICON_CORPUS[0],
            PRE_SILICON_CORPUS[7],
            PRE_SILICON_CORPUS[-1],
            PRE_SILICON_CORPUS[0],
        ):
            with self.subTest(case=case.label):
                _, raw = self._run(case)
                self.assertEqual(
                    abi.parse_result(raw, case.request_id),
                    list(noise_ntt_reference(case.sigma, case.counter)),
                )

    def test_bad_descriptor_and_bad_token_have_zero_payload(self) -> None:
        case = PRE_SILICON_CORPUS[1]
        descriptor = bytearray(abi.build_descriptor(case.counter, case.request_id))
        descriptor[5] = 2
        for label, descriptor_arg, mutator in (
            ("descriptor", bytes(descriptor), None),
            ("sequence", None, lambda token: struct.pack_into("<H", token, 4, 1)),
            ("length", None, lambda token: struct.pack_into("<H", token, 6, 191)),
            ("status", None, lambda token: struct.pack_into("<I", token, 8, 99)),
            ("reserved", None, lambda token: token.__setitem__(12, 1)),
        ):
            with self.subTest(label=label):
                _, raw = self._run(case, descriptor_arg, mutator)
                with self.assertRaises(abi.Dr2bOperationError):
                    abi.parse_result(raw, case.request_id)
                self.assertEqual(raw[abi.RESULT_HEADER_BYTES :], b"\x00" * 512)


if __name__ == "__main__":
    unittest.main()
