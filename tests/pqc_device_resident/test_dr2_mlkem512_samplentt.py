"""Off-hardware exact-output and fail-closed tests for DR2a.

The compiled C++ harness builds the production-local workers and compares their
complete terminal results to the independent hashlib/FIPS 203 oracle.  It does
not attempt native Phoenix execution.
"""

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

from phoenix_sdr_dsp.pqc import dr2_mlkem512_samplentt_abi as abi
from phoenix_sdr_dsp.pqc import dr2_mlkem512_samplentt_graph as graph
from tests.pqc_device_resident.dr2a_reference import (
    BLOCK_CAP,
    accepted_candidates_from_stream,
    samplentt_reference,
    shake128_stream_reference,
)

KERNELS = REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels"


@dataclass(frozen=True)
class CorpusCase:
    """One fixed pre-silicon SampleNTT request."""

    label: str
    rho: bytes
    j: int
    i: int
    request_id: int


def _varied_rho(case: int) -> bytes:
    return bytes(
        (0xA7 + 19 * case + 29 * index + 5 * case * index) & 0xFF
        for index in range(32)
    )


def _pre_silicon_corpus() -> tuple[CorpusCase, ...]:
    common_rho = bytes(range(32))
    cases = [
        CorpusCase(f"base-j{j}-i{i}", common_rho, j, i, 0xD2A00000 + 2 * j + i)
        for j in range(2)
        for i in range(2)
    ]
    cases.extend(
        CorpusCase(
            f"varied-{case:02d}",
            _varied_rho(case),
            (3 * case + 1) % 2,
            (case * case + case + 1) % 2,
            0xD2A10000 + case,
        )
        for case in range(8)
    )
    cases.append(
        CorpusCase(
            "boundary-alternating-00-ff",
            bytes(0 if index % 2 == 0 else 0xFF for index in range(32)),
            1,
            0,
            0xD2A20000,
        )
    )
    assert len(cases) == 13
    return tuple(cases)


PRE_SILICON_CORPUS = _pre_silicon_corpus()


class DR2aReferenceTests(unittest.TestCase):
    def test_five_blocks_mean_exactly_280_fips203_candidate_iterations(self) -> None:
        self.assertEqual(BLOCK_CAP, 5)
        self.assertEqual(BLOCK_CAP * 168 // 3, 280)
        self.assertEqual(abi.FIPS203_CANDIDATE_ITERATION_CAP, 280)

    def test_independent_reference_handles_all_mlkem512_coordinates(self) -> None:
        rho = bytes(range(32))
        results = [samplentt_reference(rho, j, i) for j in range(2) for i in range(2)]
        self.assertTrue(all(not result.limit_exceeded for result in results))
        self.assertTrue(all(result.accepted_count == 256 for result in results))
        self.assertTrue(all(result.blocks_executed == 5 for result in results))
        self.assertEqual(
            results[0].coefficients[:8],
            (481, 1919, 1434, 2359, 327, 1066, 3001, 649),
        )

    def test_shorter_reference_specialization_is_an_explicit_limit_failure(self) -> None:
        result = samplentt_reference(bytes(range(32)), 0, 0, max_blocks=1)
        self.assertTrue(result.limit_exceeded)
        self.assertEqual((result.coefficients, result.accepted_count), ((), 0))


class DR2aAbiTests(unittest.TestCase):
    def test_descriptor_layout_is_exact(self) -> None:
        descriptor = abi.build_descriptor(1, 0, 0x78563412)
        self.assertEqual(len(descriptor), 16)
        self.assertEqual(
            descriptor,
            bytes(
                (
                    1,
                    0x21,
                    0x52,
                    0,
                    1,
                    0,
                    5,
                    0,
                    0x12,
                    0x34,
                    0x56,
                    0x78,
                    0,
                    0,
                    0,
                    0,
                )
            ),
        )

    def test_malformed_public_inputs_fail_before_iron_loading(self) -> None:
        original = graph._load_iron
        graph._load_iron = lambda: (_ for _ in ()).throw(AssertionError("IRON loaded"))
        try:
            with self.assertRaises(abi.Dr2aAbiError):
                graph.run_mlkem512_samplentt(b"x" * 31, 0, 0, 0)
            with self.assertRaises(abi.Dr2aAbiError):
                graph.run_mlkem512_samplentt(b"x" * 32, 2, 0, 0)
            with self.assertRaises(TypeError):
                graph.run_mlkem512_samplentt(b"x" * 32, True, 0, 0)
            with self.assertRaises(abi.Dr2aAbiError):
                graph.run_mlkem512_samplentt(b"x" * 32, 0, 0, 1 << 32)
        finally:
            graph._load_iron = original

    def test_terminal_sentinel_and_errors_fail_closed(self) -> None:
        with self.assertRaises(abi.Dr2aAbiError):
            abi.parse_result(abi.result_sentinel(), 7)

        error = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHBB",
            error,
            0,
            abi.RESULT_MAGIC,
            7,
            abi.STATUS_LIMIT_EXCEEDED,
            0,
            abi.BLOCK_CAP,
            0,
        )
        with self.assertRaises(abi.Dr2aOperationError):
            abi.parse_result(error, 7)
        struct.pack_into("<h", error, abi.RESULT_HEADER_BYTES, 1)
        with self.assertRaises(abi.Dr2aAbiError):
            abi.parse_result(error, 7)

    def test_success_requires_complete_header_and_canonical_lanes(self) -> None:
        result = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHBB",
            result,
            0,
            abi.RESULT_MAGIC,
            9,
            abi.STATUS_OK,
            256,
            abi.BLOCK_CAP,
            0,
        )
        for lane in range(256):
            struct.pack_into("<h", result, abi.RESULT_HEADER_BYTES + 2 * lane, lane)
        self.assertEqual(abi.parse_result(result, 9)[:3], [0, 1, 2])
        struct.pack_into("<h", result, abi.RESULT_HEADER_BYTES, abi.Q)
        with self.assertRaises(abi.Dr2aAbiError):
            abi.parse_result(result, 9)


@unittest.skipUnless(shutil.which("g++"), "requires g++ host compiler")
class DR2aProductionKernelHarnessTests(unittest.TestCase):
    """Compile both production workers and compare the complete ABI to hashlib."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="dr2a-kernel-test-")
        library = Path(cls._directory.name) / "dr2a_kernels.so"
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
                str(KERNELS / "dr2_mlkem512_shake128_service.cc"),
                str(KERNELS / "dr2_mlkem512_samplentt.cc"),
                "-o",
                str(library),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.library = ctypes.CDLL(str(library))
        cls.rho_type = ctypes.c_uint8 * abi.RHO_BYTES
        cls.descriptor_type = ctypes.c_uint8 * abi.DESCRIPTOR_BYTES
        cls.block_type = ctypes.c_uint8 * abi.XOF_BLOCK_BYTES
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

    def _produce_blocks(self, case: CorpusCase) -> list[bytes]:
        descriptor = abi.build_descriptor(case.j, case.i, case.request_id)
        blocks: list[bytes] = []
        for _ in range(abi.BLOCK_CAP):
            output = self.block_type()
            self.library.dr2a_shake128_emit_next(
                self.rho_type.from_buffer_copy(case.rho),
                self.descriptor_type.from_buffer_copy(descriptor),
                output,
            )
            blocks.append(bytes(output))
        return blocks

    def _consume_all_blocks(self, blocks: list[bytes | bytearray]) -> bytes:
        self.assertEqual(len(blocks), abi.BLOCK_CAP)
        result = self.result_type()
        for block in blocks:
            self.library.dr2a_samplentt_consume_next(
                self.block_type.from_buffer_copy(block), result
            )
        return bytes(result)

    def test_full_compiled_production_corpus_matches_hashlib_exactly(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                blocks = self._produce_blocks(case)
                raw = self._consume_all_blocks(blocks)
                expected_stream = shake128_stream_reference(case.rho, case.j, case.i)
                expected = samplentt_reference(case.rho, case.j, case.i)
                self.assertFalse(expected.limit_exceeded)
                self.assertEqual(
                    b"".join(token[12:] for token in blocks), expected_stream
                )
                self.assertEqual(
                    abi.parse_result(raw, case.request_id), list(expected.coefficients)
                )

    def test_repeated_requests_reset_producer_and_sampler_state(self) -> None:
        for case in (PRE_SILICON_CORPUS[0], PRE_SILICON_CORPUS[7], PRE_SILICON_CORPUS[-1]):
            with self.subTest(case=case.label):
                blocks = self._produce_blocks(case)
                raw = self._consume_all_blocks(blocks)
                self.assertEqual(
                    b"".join(token[12:] for token in blocks),
                    shake128_stream_reference(case.rho, case.j, case.i),
                )
                self.assertEqual(
                    abi.parse_result(raw, case.request_id),
                    list(samplentt_reference(case.rho, case.j, case.i).coefficients),
                )

    def test_corrupt_tokens_still_drain_all_five_and_fail_closed(self) -> None:
        case = PRE_SILICON_CORPUS[2]
        corruptions = (
            ("wrong_sequence", 3, 4, "<H", 99),
            ("wrong_request_id", 4, 0, "<I", case.request_id ^ 0x01020304),
            ("wrong_producer_status", 2, 8, "<I", 99),
            ("wrong_bytes_valid", 1, 6, "<H", 167),
        )
        for _label, block_index, offset, format_string, value in corruptions:
            with self.subTest(corruption=_label):
                blocks = [bytearray(token) for token in self._produce_blocks(case)]
                struct.pack_into(format_string, blocks[block_index], offset, value)
                raw = self._consume_all_blocks(blocks)
                with self.assertRaises(abi.Dr2aOperationError):
                    abi.parse_result(raw, case.request_id)
                self.assertEqual(raw[abi.RESULT_HEADER_BYTES :], b"\x00" * 512)

    def test_all_rejected_data_reaches_bounded_limit_error_with_zero_payload(self) -> None:
        case = PRE_SILICON_CORPUS[0]
        blocks = [bytearray(token) for token in self._produce_blocks(case)]
        for block in blocks:
            block[12:] = b"\xFF" * abi.XOF_DATA_BYTES
        raw = self._consume_all_blocks(blocks)
        with self.assertRaises(abi.Dr2aOperationError):
            abi.parse_result(raw, case.request_id)
        header = struct.unpack_from("<IIIHBB", raw)
        self.assertEqual(
            header,
            (
                abi.RESULT_MAGIC,
                case.request_id,
                abi.STATUS_LIMIT_EXCEEDED,
                0,
                abi.BLOCK_CAP,
                0,
            ),
        )
        self.assertEqual(raw[abi.RESULT_HEADER_BYTES :], b"\x00" * 512)

    def test_success_freezes_first_256_but_consumes_all_five_blocks(self) -> None:
        case = PRE_SILICON_CORPUS[-1]
        blocks = self._produce_blocks(case)
        raw = self._consume_all_blocks(blocks)
        all_accepted = accepted_candidates_from_stream(
            shake128_stream_reference(case.rho, case.j, case.i)
        )
        self.assertGreater(len(all_accepted), abi.N)
        self.assertEqual(
            abi.parse_result(raw, case.request_id), list(all_accepted[: abi.N])
        )


if __name__ == "__main__":
    unittest.main()
