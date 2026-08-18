"""DR2d host harness: complete byte-exact K-PKE.KeyGen and fail-closed ABI."""

from __future__ import annotations

import _ctypes
import ctypes
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_abi as abi
from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph as graph
from tests.pqc_device_resident.dr2b_reference import noise_ntt_reference
from tests.pqc_device_resident.dr2d_reference import (
    kpke_keygen_reference,
    multiply_ntts_reference,
    sample_ntt_reference,
)

KERNELS = REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels"
ACVP_CORPUS = (
    REPO_ROOT
    / "tests"
    / "pqc_device_resident"
    / "data"
    / "dr2d_nist_acvp_mlkem512_kpke_keygen_25.json"
)
ACVP_SOURCE = (
    "https://github.com/usnistgov/ACVP-Server/tree/"
    "975de31eb83d87039ec88934fdc47d8c312b892d/"
    "gen-val/json-files/ML-KEM-keyGen-FIPS203"
)
ACVP_COMMIT = "975de31eb83d87039ec88934fdc47d8c312b892d"


@dataclass(frozen=True)
class CorpusCase:
    label: str
    d: bytes
    request_id: int


_ACVP_DATA = json.loads(ACVP_CORPUS.read_text(encoding="utf-8"))
assert _ACVP_DATA["source"] == ACVP_SOURCE
assert _ACVP_DATA["sourceCommit"] == ACVP_COMMIT
assert _ACVP_DATA["sourceFiles"] == ["prompt.json", "expectedResults.json"]
assert _ACVP_DATA["sourceSha256"] == {
    "prompt.json": "3f9ce34f6c836c77958bad2729e837c3b213f44ac36c3065976e7acca6389523",
    "expectedResults.json": "a253d0ad91c95ebea5b409673defef0aa49d65d4ed72286399e2e798ddf073a4",
}
assert (
    _ACVP_DATA["derivation"]
    == "ekPKE is ACVP ek; dkPKE is the first 768 bytes of ACVP dk"
)
PRE_SILICON_CORPUS = tuple(
    CorpusCase(
        f"acvp-tcId-{case['tcId']:02d}",
        bytes.fromhex(case["d"]),
        0xD2D00000 + case["tcId"],
    )
    for case in _ACVP_DATA["tests"]
)
ACVP_EXPECTED = {
    case["tcId"]: (bytes.fromhex(case["ekPKE"]), bytes.fromhex(case["dkPKE"]))
    for case in _ACVP_DATA["tests"]
}
assert len(PRE_SILICON_CORPUS) == len(ACVP_EXPECTED) == 25


class DR2dReferenceTests(unittest.TestCase):
    def test_all_25_official_acvp_vectors_match_independent_fips203_reference(
        self,
    ) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                tc_id = int(case.label[-2:])
                self.assertEqual(kpke_keygen_reference(case.d), ACVP_EXPECTED[tc_id])


class DR2dAbiTests(unittest.TestCase):
    @staticmethod
    def _success_record(payload: bytes, request_id: int = 9) -> bytes:
        record = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHHI",
            record,
            0,
            abi.RESULT_MAGIC,
            request_id,
            abi.STATUS_OK,
            abi.EK_PKE_BYTES,
            abi.DK_PKE_BYTES,
            zlib.crc32(payload) & 0xFFFFFFFF,
        )
        record[abi.RESULT_HEADER_BYTES :] = payload
        return bytes(record)

    def test_host_staging_cleanup_clears_source_and_distinct_tensor_backing(
        self,
    ) -> None:
        class Tensor:
            def __init__(self, backing: np.ndarray) -> None:
                self._data = backing

        source, backing = (
            np.full(32, 0xA5, dtype=np.uint8),
            np.full(32, 0x5A, dtype=np.uint8),
        )
        graph._clear_host_staging(source, Tensor(backing))
        self.assertEqual(source.tobytes(), b"\0" * 32)
        self.assertEqual(backing.tobytes(), b"\0" * 32)

    def test_outer_cleanup_zeroes_all_staging_when_native_load_fails(self) -> None:
        cleared = []
        original_load, original_clear = graph._load_iron, graph._clear_host_staging

        def track_clear(array, tensor) -> None:
            original_clear(array, tensor)
            cleared.append(array.copy())

        graph._load_iron = lambda: (_ for _ in ()).throw(
            RuntimeError("missing runtime")
        )
        graph._clear_host_staging = track_clear
        try:
            with self.assertRaises(graph.NativeBackendUnavailable):
                graph.run_mlkem512_kpke_keygen(b"x" * 32, 9)
        finally:
            graph._load_iron, graph._clear_host_staging = original_load, original_clear
        self.assertEqual(len(cleared), 3)
        self.assertTrue(all(not np.any(array) for array in cleared))

    def test_outer_cleanup_zeroes_created_tensor_when_second_constructor_fails(
        self,
    ) -> None:
        cleared, tensors = [], []

        class Tensor:
            calls = 0

            def __init__(self, source: np.ndarray, **_kwargs) -> None:
                type(self).calls += 1
                if type(self).calls == 2:
                    raise RuntimeError(
                        "simulated descriptor tensor construction failure"
                    )
                self._data = source.copy()
                tensors.append(self)

        original_load, original_clear = graph._load_iron, graph._clear_host_staging

        def track_clear(array, tensor) -> None:
            original_clear(array, tensor)
            cleared.append(array.copy())

        graph._load_iron = lambda: (Tensor,)
        graph._clear_host_staging = track_clear
        try:
            with self.assertRaises(graph.NativeBackendUnavailable):
                graph.run_mlkem512_kpke_keygen(b"x" * 32, 9)
        finally:
            graph._load_iron, graph._clear_host_staging = original_load, original_clear
        self.assertEqual(len(tensors), 1)
        self.assertTrue(not np.any(tensors[0]._data))
        self.assertEqual(len(cleared), 3)
        self.assertTrue(all(not np.any(array) for array in cleared))

    def test_outer_cleanup_zeroes_result_staging_after_write_then_dispatch_throw(
        self,
    ) -> None:
        tensors = []

        class Tensor:
            def __init__(self, source: np.ndarray, **_kwargs) -> None:
                self._data = source.copy()
                tensors.append(self)

            def to(self, _device: str) -> None:
                return None

        def write_then_throw(*_args, **_kwargs) -> None:
            tensors[-1]._data.fill(0xA5)
            raise RuntimeError("simulated post-write dispatch failure")

        original_load, original_program = graph._load_iron, graph._program
        graph._load_iron = lambda: (Tensor,)
        graph._program = lambda: write_then_throw
        try:
            with self.assertRaises(graph.NativeBackendUnavailable):
                graph.run_mlkem512_kpke_keygen(b"x" * 32, 9)
        finally:
            graph._load_iron, graph._program = original_load, original_program
        self.assertEqual(len(tensors), 3)
        self.assertTrue(all(not np.any(tensor._data) for tensor in tensors))

    def test_exact_descriptor_and_error_record(self) -> None:
        self.assertEqual(
            abi.build_descriptor(0x78563412),
            bytes((1, 0x24, 0x52, 0, 2, 3, 5, 0, 0x12, 0x34, 0x56, 0x78, 0, 0, 0, 0)),
        )
        with self.assertRaises(abi.Dr2dAbiError):
            abi.parse_result(abi.result_sentinel(), 0)
        error = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHHI", error, 0, abi.RESULT_MAGIC, 9, abi.STATUS_BAD_TOKEN, 0, 0, 0
        )
        with self.assertRaises(abi.Dr2dOperationError):
            abi.parse_result(error, 9)

    def test_parse_rejects_committed_sentinel_partial_checksum_zero_and_noncanonical_payloads(
        self,
    ) -> None:
        valid_ek, valid_dk = ACVP_EXPECTED[1]
        valid_payload = valid_ek + valid_dk
        with self.assertRaises(abi.Dr2dAbiError):
            abi.parse_result(self._success_record(b"\xff" * len(valid_payload)), 9)

        partial = bytearray(valid_payload)
        partial[abi.EK_PKE_BYTES :] = b"\x00" * abi.DK_PKE_BYTES
        partial_record = bytearray(self._success_record(valid_payload))
        partial_record[abi.RESULT_HEADER_BYTES :] = partial
        with self.assertRaises(abi.Dr2dAbiError):
            abi.parse_result(partial_record, 9)

        bad_checksum = bytearray(self._success_record(valid_payload))
        bad_checksum[16] ^= 1
        with self.assertRaises(abi.Dr2dAbiError):
            abi.parse_result(bad_checksum, 9)

        with self.assertRaises(abi.Dr2dAbiError):
            abi.parse_result(self._success_record(b"\x00" * len(valid_payload)), 9)

        noncanonical = bytearray(valid_payload)
        noncanonical[0:3] = b"\xff\x0f\x00"  # First packed 12-bit t_hat lane is 4095.
        with self.assertRaises(abi.Dr2dAbiError):
            abi.parse_result(self._success_record(noncanonical), 9)

    def test_bad_input_precedes_native_loading(self) -> None:
        original = graph._load_iron
        graph._load_iron = lambda: (_ for _ in ()).throw(AssertionError("IRON loaded"))
        try:
            with self.assertRaises(abi.Dr2dAbiError):
                graph.run_mlkem512_kpke_keygen(b"x" * 31, 0)
            with self.assertRaises(TypeError):
                graph.run_mlkem512_kpke_keygen(b"x" * 32, True)
        finally:
            graph._load_iron = original


@unittest.skipUnless(shutil.which("g++"), "requires g++ host compiler")
class DR2dProductionKernelHarnessTests(unittest.TestCase):
    """Independent host linkage harness for every partitioned production kernel."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="dr2d-kernel-test-")
        library = Path(cls._directory.name) / "dr2d_partitioned_kernels.so"
        sources = [
            "dr2d_mlkem512_kpke_keygen_seed.cc",
            "dr2d_mlkem512_kpke_keygen_row0_expand.cc",
            "dr2d_mlkem512_kpke_keygen_row0_accumulate.cc",
            "dr2d_mlkem512_kpke_keygen_row1_expand.cc",
            "dr2d_mlkem512_kpke_keygen_row1_accumulate.cc",
            "dr2d_mlkem512_kpke_keygen_serialize.cc",
        ]
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
                *(str(KERNELS / source) for source in sources),
                "-o",
                str(library),
            ],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        cls.library = ctypes.CDLL(str(library))
        cls.d_type = ctypes.c_uint8 * abi.D_BYTES
        cls.descriptor_type = ctypes.c_uint8 * abi.DESCRIPTOR_BYTES
        cls.secret_type = ctypes.c_uint8 * abi.SECRET_TOKEN_BYTES
        cls.matrix_type = ctypes.c_uint8 * abi.ROW_MATRIX_TOKEN_BYTES
        cls.state_type = ctypes.c_uint8 * abi.ROW_STATE_TOKEN_BYTES
        cls.final_type = ctypes.c_uint8 * abi.PRIVATE_TOKEN_BYTES
        cls.result_type = ctypes.c_uint8 * abi.RESULT_BYTES
        cls.library.dr2d_kpke_keygen_seed_noise.argtypes = [
            ctypes.POINTER(cls.d_type),
            ctypes.POINTER(cls.descriptor_type),
            ctypes.POINTER(cls.secret_type),
        ]
        cls.library.dr2d_kpke_keygen_row0_expand.argtypes = [
            ctypes.POINTER(cls.secret_type),
            ctypes.POINTER(cls.matrix_type),
        ]
        cls.library.dr2d_kpke_keygen_row0_accumulate.argtypes = [
            ctypes.POINTER(cls.matrix_type),
            ctypes.POINTER(cls.state_type),
        ]
        cls.library.dr2d_kpke_keygen_row1_expand.argtypes = [
            ctypes.POINTER(cls.state_type),
            ctypes.POINTER(cls.matrix_type),
        ]
        cls.library.dr2d_kpke_keygen_row1_accumulate.argtypes = [
            ctypes.POINTER(cls.matrix_type),
            ctypes.POINTER(cls.final_type),
        ]
        cls.library.dr2d_kpke_keygen_serialize.argtypes = [
            ctypes.POINTER(cls.final_type),
            ctypes.POINTER(cls.result_type),
        ]

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
        self,
        case: CorpusCase,
        descriptor: bytes | None = None,
        corrupt_at: str | None = None,
    ) -> dict[str, bytes]:
        d = self.d_type.from_buffer_copy(case.d)
        descriptor_buffer = self.descriptor_type.from_buffer_copy(
            descriptor or abi.build_descriptor(case.request_id)
        )
        secret, row0_matrix, state = (
            self.secret_type(),
            self.matrix_type(),
            self.state_type(),
        )
        row1_matrix, final_token, result = (
            self.matrix_type(),
            self.final_type(),
            self.result_type(),
        )
        self.library.dr2d_kpke_keygen_seed_noise(d, descriptor_buffer, secret)
        seed_snapshot = bytes(secret)
        if corrupt_at == "secret":
            secret[8] ^= 1
        if corrupt_at == "secret_status":
            secret[4] = 0xFF
        self.library.dr2d_kpke_keygen_row0_expand(secret, row0_matrix)
        row0_matrix_snapshot = bytes(row0_matrix)
        if corrupt_at == "row0_matrix":
            row0_matrix[8] ^= 1
        if corrupt_at == "row0_matrix_status":
            row0_matrix[4] = 0xFF
        self.library.dr2d_kpke_keygen_row0_accumulate(row0_matrix, state)
        state_snapshot = bytes(state)
        if corrupt_at == "row_state":
            state[8] ^= 1
        if corrupt_at == "row_state_status":
            state[4] = 0xFF
        self.library.dr2d_kpke_keygen_row1_expand(state, row1_matrix)
        row1_matrix_snapshot = bytes(row1_matrix)
        if corrupt_at == "row1_matrix":
            row1_matrix[8] ^= 1
        if corrupt_at == "row1_matrix_status":
            row1_matrix[4] = 0xFF
        self.library.dr2d_kpke_keygen_row1_accumulate(row1_matrix, final_token)
        final_snapshot = bytes(final_token)
        if corrupt_at == "final":
            final_token[8] ^= 1
        if corrupt_at == "final_status":
            final_token[4] = 0xFF
        self.library.dr2d_kpke_keygen_serialize(final_token, result)
        return {
            "d": bytes(d),
            "descriptor": bytes(descriptor_buffer),
            "seed_snapshot": seed_snapshot,
            "row0_matrix_snapshot": row0_matrix_snapshot,
            "state_snapshot": state_snapshot,
            "row1_matrix_snapshot": row1_matrix_snapshot,
            "final_snapshot": final_snapshot,
            "secret": bytes(secret),
            "row0_matrix": bytes(row0_matrix),
            "state": bytes(state),
            "row1_matrix": bytes(row1_matrix),
            "final": bytes(final_token),
            "result": bytes(result),
        }

    def test_all_25_partitioned_production_keygens_match_independent_reference(
        self,
    ) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                records = self._run(case)
                tc_id = int(case.label[-2:])
                self.assertEqual(
                    abi.parse_result(records["result"], case.request_id),
                    ACVP_EXPECTED[tc_id],
                )
                rho_sigma = hashlib.sha3_512(case.d + bytes((abi.K,))).digest()
                self.assertEqual(records["seed_snapshot"][16:48], rho_sigma[:32])
                for counter, offset in enumerate((48, 560, 1072, 1584)):
                    with self.subTest(case=case.label, counter=counter):
                        self.assertEqual(
                            struct.unpack_from(
                                "<256H", records["seed_snapshot"], offset
                            ),
                            noise_ntt_reference(rho_sigma[32:], counter),
                        )

    def test_all_consumed_ingress_and_private_tokens_are_zeroized_after_success(
        self,
    ) -> None:
        records = self._run(PRE_SILICON_CORPUS[0])
        for name in (
            "d",
            "descriptor",
            "secret",
            "row0_matrix",
            "state",
            "row1_matrix",
            "final",
        ):
            with self.subTest(record=name):
                self.assertEqual(records[name], b"\0" * len(records[name]))

    def test_bad_descriptor_propagates_fixed_zero_error_and_clears_every_stage(
        self,
    ) -> None:
        case = PRE_SILICON_CORPUS[0]
        bad = bytearray(abi.build_descriptor(case.request_id))
        bad[5] = 2
        records = self._run(case, bytes(bad))
        for name in (
            "d",
            "descriptor",
            "secret",
            "row0_matrix",
            "state",
            "row1_matrix",
            "final",
        ):
            self.assertEqual(records[name], b"\0" * len(records[name]))
        with self.assertRaises(abi.Dr2dOperationError):
            abi.parse_result(records["result"], case.request_id)
        self.assertEqual(
            records["result"][abi.RESULT_HEADER_BYTES :],
            b"\0" * (abi.RESULT_BYTES - abi.RESULT_HEADER_BYTES),
        )

    def test_each_private_fifo_trust_boundary_rejects_status_corruption(self) -> None:
        case = PRE_SILICON_CORPUS[0]
        for boundary in (
            "secret_status",
            "row0_matrix_status",
            "row_state_status",
            "row1_matrix_status",
            "final_status",
        ):
            with self.subTest(boundary=boundary):
                records = self._run(case, corrupt_at=boundary)
                with self.assertRaises(abi.Dr2dOperationError):
                    abi.parse_result(records["result"], case.request_id)
                self.assertEqual(
                    records["result"][abi.RESULT_HEADER_BYTES :],
                    b"\0" * (abi.RESULT_BYTES - abi.RESULT_HEADER_BYTES),
                )

    # ------------------------------------------------------------------
    # Directed regressions for the repaired full-word coefficient stores.
    #
    # Every normal-path coefficient store below now commits one aligned 32-bit
    # word per coefficient pair (or per copied word) instead of a 16-bit or
    # 8-bit store, because the installed Peano (llvm-aie 21.0.0 commit
    # c9c5ecb7, ancestral to upstream fix f1baf5a / PR #1221) drops the high
    # half of a sub-word store scheduled into a zero-overhead-loop end bundle.
    # These tests force nonzero high bytes and nonzero bit-8..11 nibbles
    # through both halves of every repaired word and pin every repaired region
    # to the independent oracle, so a lost or truncated high half cannot pass.
    #
    # Scope is destination-classified: only coefficient-bearing and
    # polynomial-carry token regions are word-stored.  The 32-byte token `rho`
    # copies, local Keccak/SHAKE/PRF state, header fields, volatile
    # zeroization, and the serializer keep their byte stores on purpose, and
    # `rho` is still checked for exactness below through its byte-copy path.
    # ------------------------------------------------------------------
    REPAIRED_REGIONS = (
        # (label, snapshot key, byte offset) - one per repaired store path.
        ("w0-cbd3-ntt-store-s0", "seed_snapshot", 48),
        ("w0-cbd3-ntt-store-s1", "seed_snapshot", 560),
        ("w0-cbd3-ntt-store-e0", "seed_snapshot", 1072),
        ("w0-cbd3-ntt-store-e1", "seed_snapshot", 1584),
        ("w1-copy-words-secret", "row0_matrix_snapshot", 48),
        ("w1-copy-words-s1", "row0_matrix_snapshot", 560),
        ("w1-copy-words-e0", "row0_matrix_snapshot", 1072),
        ("w1-copy-words-e1", "row0_matrix_snapshot", 1584),
        ("w1-sample-matrix-store-a00", "row0_matrix_snapshot", 2096),
        ("w1-sample-matrix-store-a01", "row0_matrix_snapshot", 2608),
        ("w2-copy-words-secret", "state_snapshot", 48),
        ("w2-copy-words-s1", "state_snapshot", 560),
        ("w2-add-product-ntt-t0", "state_snapshot", 1072),
        ("w2-copy-words-e1", "state_snapshot", 1584),
        ("w3-copy-words-secret", "row1_matrix_snapshot", 48),
        ("w3-copy-words-s1", "row1_matrix_snapshot", 560),
        ("w3-sample-matrix-store-a10", "row1_matrix_snapshot", 2096),
        ("w3-sample-matrix-store-a11", "row1_matrix_snapshot", 2608),
        ("w4-copy-words-s0", "final_snapshot", 64),
        ("w4-copy-words-s1", "final_snapshot", 576),
        ("w4-copy-words-t0", "final_snapshot", 1088),
        ("w4-add-product-ntt-t1", "final_snapshot", 1600),
    )
    # Canonical lanes are 0..Q-1 == 0..3328, so bits 8..11 range over 0x0..0xD
    # and every value except the single-lane 0xD case must be observed.
    REQUIRED_UPPER_NIBBLES = frozenset(range(13))
    LEGAL_UPPER_NIBBLES = frozenset(range(14))

    @staticmethod
    def _lanes(record: bytes, offset: int) -> tuple[int, ...]:
        return struct.unpack_from("<256H", record, offset)

    def _oracle_regions(self, d: bytes) -> dict[str, tuple[int, ...]]:
        rho_sigma = hashlib.sha3_512(d + bytes((abi.K,))).digest()
        rho, sigma = rho_sigma[:32], rho_sigma[32:]
        noise = tuple(noise_ntt_reference(sigma, counter) for counter in range(4))
        a = {
            (column, row): sample_ntt_reference(rho, column, row)
            for column in range(2)
            for row in range(2)
        }
        t_hat = []
        for row in range(2):
            p0 = multiply_ntts_reference(a[(0, row)], noise[0])
            p1 = multiply_ntts_reference(a[(1, row)], noise[1])
            error = noise[row + 2]
            t_hat.append(tuple((p0[i] + p1[i] + error[i]) % 3329 for i in range(256)))
        return {
            "rho": rho,
            "w0-cbd3-ntt-store-s0": noise[0],
            "w0-cbd3-ntt-store-s1": noise[1],
            "w0-cbd3-ntt-store-e0": noise[2],
            "w0-cbd3-ntt-store-e1": noise[3],
            "w1-copy-words-secret": noise[0],
            "w1-copy-words-s1": noise[1],
            "w1-copy-words-e0": noise[2],
            "w1-copy-words-e1": noise[3],
            "w1-sample-matrix-store-a00": a[(0, 0)],
            "w1-sample-matrix-store-a01": a[(1, 0)],
            "w2-copy-words-secret": noise[0],
            "w2-copy-words-s1": noise[1],
            "w2-add-product-ntt-t0": t_hat[0],
            "w2-copy-words-e1": noise[3],
            "w3-copy-words-secret": noise[0],
            "w3-copy-words-s1": noise[1],
            "w3-sample-matrix-store-a10": a[(0, 1)],
            "w3-sample-matrix-store-a11": a[(1, 1)],
            "w4-copy-words-s0": noise[0],
            "w4-copy-words-s1": noise[1],
            "w4-copy-words-t0": t_hat[0],
            "w4-add-product-ntt-t1": t_hat[1],
        }

    def test_every_repaired_full_word_store_forces_high_bytes_in_both_word_halves(
        self,
    ) -> None:
        """Both 16-bit halves of every repaired 32-bit store carry high bytes.

        A sub-word store whose high byte were dropped in a ZOL loop-end bundle
        would leave that lane below 0x100, so every repaired path is required
        to have carried each canonical bit-8..11 nibble and to have carried
        nonzero high bytes on even and odd lanes alike.
        """
        nibbles = {label: set() for label, _key, _offset in self.REPAIRED_REGIONS}
        even_high = {label: 0 for label, _key, _offset in self.REPAIRED_REGIONS}
        odd_high = {label: 0 for label, _key, _offset in self.REPAIRED_REGIONS}
        for case in PRE_SILICON_CORPUS:
            records = self._run(case)
            for label, key, offset in self.REPAIRED_REGIONS:
                lanes = self._lanes(records[key], offset)
                self.assertEqual(len(lanes), 256, label)
                nibbles[label].update(lane >> 8 for lane in lanes)
                even_high[label] += sum(1 for lane in lanes[0::2] if lane >= 0x100)
                odd_high[label] += sum(1 for lane in lanes[1::2] if lane >= 0x100)
        for label, _key, _offset in self.REPAIRED_REGIONS:
            with self.subTest(store_path=label):
                self.assertLessEqual(nibbles[label], self.LEGAL_UPPER_NIBBLES)
                self.assertLessEqual(self.REQUIRED_UPPER_NIBBLES, nibbles[label])
                self.assertGreater(even_high[label], 0)
                self.assertGreater(odd_high[label], 0)

    def test_every_repaired_store_region_matches_the_independent_oracle_exactly(
        self,
    ) -> None:
        """Pin all 22 repaired regions to the independent FIPS 203 oracle.

        This is the byte-exactness half of the high-byte contract: a lost,
        truncated, or transposed high half in cbd3_ntt_store_dr2b,
        sample_matrix_store, copy_words, or add_product_ntt changes at least
        one lane here for every ACVP case.
        """
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                records = self._run(case)
                oracle = self._oracle_regions(case.d)
                for label, key, offset in self.REPAIRED_REGIONS:
                    with self.subTest(store_path=label):
                        self.assertEqual(
                            self._lanes(records[key], offset), oracle[label]
                        )
                # rho is NOT part of the repair: it keeps its physically
                # validated 32-byte byte-copy loops.  Its exactness is still
                # required at every stage so the narrowed scope cannot silently
                # break the ek suffix.
                for key, offset in (
                    ("seed_snapshot", 16),
                    ("row0_matrix_snapshot", 16),
                    ("state_snapshot", 16),
                    ("row1_matrix_snapshot", 16),
                    ("final_snapshot", 32),
                ):
                    with self.subTest(rho_in=key):
                        self.assertEqual(
                            records[key][offset : offset + 32], oracle["rho"]
                        )

    def _misaligned(self, array_type, payload: bytes = b""):
        """Return (backing, pointer) for a deliberately 1-byte-misaligned token."""
        size = ctypes.sizeof(array_type)
        backing = (ctypes.c_uint8 * (size + 4)).from_buffer_copy(
            b"\0" + payload.ljust(size, b"\0") + b"\0\0\0"
        )
        self.assertEqual(ctypes.addressof(backing) % 4, 0)
        pointer = ctypes.cast(ctypes.byref(backing, 1), ctypes.POINTER(array_type))
        self.assertEqual(ctypes.addressof(pointer.contents) % 4, 1)
        return backing, pointer

    def test_misaligned_token_base_fails_closed_in_every_repaired_worker(self) -> None:
        """Every repaired worker rejects a non-32-bit-aligned token base.

        The repaired full-word stores are only well defined on a 32-bit
        aligned base, so each worker validates its token bases before storing
        and fails closed with STATUS_BAD_TOKEN and an all-zero payload.  This
        also proves the guards are reachable rather than dead code.
        """
        case = PRE_SILICON_CORPUS[0]
        good = self._run(case)

        d = self.d_type.from_buffer_copy(case.d)
        descriptor = self.descriptor_type.from_buffer_copy(
            abi.build_descriptor(case.request_id)
        )
        _hold, misaligned_secret = self._misaligned(self.secret_type)
        self.library.dr2d_kpke_keygen_seed_noise(d, descriptor, misaligned_secret)
        with self.subTest(worker="seed-noise", misaligned="secret-out"):
            record = bytes(misaligned_secret.contents)
            self.assertEqual(
                struct.unpack_from("<I", record, 4)[0], abi.STATUS_BAD_TOKEN
            )
            self.assertEqual(record[8:], b"\0" * (len(record) - 8))
            self.assertEqual(bytes(d), b"\0" * abi.D_BYTES)
            self.assertEqual(bytes(descriptor), b"\0" * abi.DESCRIPTOR_BYTES)

        for worker, function, in_type, in_payload, out_type in (
            (
                "row0-expand",
                self.library.dr2d_kpke_keygen_row0_expand,
                self.secret_type,
                good["seed_snapshot"],
                self.matrix_type,
            ),
            (
                "row0-accumulate",
                self.library.dr2d_kpke_keygen_row0_accumulate,
                self.matrix_type,
                good["row0_matrix_snapshot"],
                self.state_type,
            ),
            (
                "row1-expand",
                self.library.dr2d_kpke_keygen_row1_expand,
                self.state_type,
                good["state_snapshot"],
                self.matrix_type,
            ),
            (
                "row1-accumulate",
                self.library.dr2d_kpke_keygen_row1_accumulate,
                self.matrix_type,
                good["row1_matrix_snapshot"],
                self.final_type,
            ),
        ):
            for misaligned_side in ("output", "input"):
                with self.subTest(worker=worker, misaligned=misaligned_side):
                    if misaligned_side == "output":
                        source = in_type.from_buffer_copy(in_payload)
                        _out_hold, out_arg = self._misaligned(out_type)
                        function(source, out_arg)
                        record = bytes(out_arg.contents)
                    else:
                        _in_hold, source = self._misaligned(in_type, in_payload)
                        out_buffer = out_type()
                        function(source, out_buffer)
                        record = bytes(out_buffer)
                    self.assertEqual(
                        struct.unpack_from("<I", record, 4)[0],
                        abi.STATUS_BAD_TOKEN,
                        "misaligned token base must fail closed as BAD_TOKEN",
                    )
                    self.assertEqual(record[8:], b"\0" * (len(record) - 8))

    def test_serializer_rejects_every_fail_closed_repaired_worker_record(self) -> None:
        """A fail-closed BAD_TOKEN token still reaches a committed error record."""
        _hold, misaligned_final = self._misaligned(self.final_type)
        d = self.d_type.from_buffer_copy(PRE_SILICON_CORPUS[0].d)
        descriptor = self.descriptor_type.from_buffer_copy(
            abi.build_descriptor(PRE_SILICON_CORPUS[0].request_id)
        )
        secret = self.secret_type()
        self.library.dr2d_kpke_keygen_seed_noise(d, descriptor, secret)
        matrix, state = self.matrix_type(), self.state_type()
        self.library.dr2d_kpke_keygen_row0_expand(secret, matrix)
        self.library.dr2d_kpke_keygen_row0_accumulate(matrix, state)
        row1_matrix = self.matrix_type()
        self.library.dr2d_kpke_keygen_row1_expand(state, row1_matrix)
        self.library.dr2d_kpke_keygen_row1_accumulate(row1_matrix, misaligned_final)
        result = self.result_type()
        aligned_final = self.final_type.from_buffer_copy(
            bytes(misaligned_final.contents)
        )
        self.library.dr2d_kpke_keygen_serialize(aligned_final, result)
        with self.assertRaises(abi.Dr2dOperationError):
            abi.parse_result(bytes(result), PRE_SILICON_CORPUS[0].request_id)
        self.assertEqual(
            bytes(result)[abi.RESULT_HEADER_BYTES :],
            b"\0" * (abi.RESULT_BYTES - abi.RESULT_HEADER_BYTES),
        )
        self.assertEqual(bytes(aligned_final), b"\0" * abi.PRIVATE_TOKEN_BYTES)

    def test_each_private_fifo_trust_boundary_rejects_reserved_corruption_and_zeroizes(
        self,
    ) -> None:
        case = PRE_SILICON_CORPUS[0]
        for boundary in ("secret", "row0_matrix", "row_state", "row1_matrix", "final"):
            with self.subTest(boundary=boundary):
                records = self._run(case, corrupt_at=boundary)
                for name in (
                    "d",
                    "descriptor",
                    "secret",
                    "row0_matrix",
                    "state",
                    "row1_matrix",
                    "final",
                ):
                    self.assertEqual(records[name], b"\0" * len(records[name]))
                with self.assertRaises(abi.Dr2dOperationError):
                    abi.parse_result(records["result"], case.request_id)
                self.assertEqual(
                    records["result"][abi.RESULT_HEADER_BYTES :],
                    b"\0" * (abi.RESULT_BYTES - abi.RESULT_HEADER_BYTES),
                )


if __name__ == "__main__":
    unittest.main()
