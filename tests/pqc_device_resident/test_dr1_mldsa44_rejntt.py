"""Off-hardware exact-output and malformed-ABI tests for DR1.

Native silicon execution is deliberately not attempted here.  The host C++
harness compiles the production-local kernels and compares their terminal
output against the independent hashlib oracle in ``dr1_reference``.
"""

from __future__ import annotations

import _ctypes
import ctypes
import hashlib
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

from phoenix_sdr_dsp.pqc import dr1_abi as abi
from phoenix_sdr_dsp.pqc import dr1_mldsa44_rejntt_graph as graph
from tests.pqc_device_resident.dr1_reference import (
    accepted_candidates_from_stream,
    expanda_rejntt_reference,
    shake128_stream_reference,
)

KERNELS = REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels"


@dataclass(frozen=True)
class CorpusCase:
    """One fixed pre-silicon request; fixtures below are test-only guards."""

    label: str
    rho: bytes
    j: int
    i: int
    request_id: int


def _varied_rho(case: int) -> bytes:
    """Deterministic non-repeating rho fixture without production dependencies."""
    return bytes(
        (0x5D + 41 * case + 17 * index + 3 * case * index) & 0xFF for index in range(32)
    )


def _pre_silicon_corpus() -> tuple[CorpusCase, ...]:
    common_rho = bytes(range(32))
    cases = [
        CorpusCase(f"base-j{j}-i{i}", common_rho, j, i, 0xD1000000 + 4 * j + i)
        for j in range(4)
        for i in range(4)
    ]
    cases.extend(
        CorpusCase(
            f"varied-{case:02d}",
            _varied_rho(case),
            (3 * case + 1) % 4,
            (case * case + 2 * case + 3) % 4,
            0xD2000000 + case,
        )
        for case in range(16)
    )
    cases.append(
        CorpusCase(
            "boundary-alternating-00-ff",
            bytes(0 if index % 2 == 0 else 0xFF for index in range(32)),
            3,
            2,
            0xD3000000,
        )
    )
    assert len(cases) == 33
    return tuple(cases)


PRE_SILICON_CORPUS = _pre_silicon_corpus()

# Independently generated, test-only SHA-256 values of little-endian
# ``<256i`` coefficient payloads.  They are deliberately compact fixtures:
# the live hashlib oracle remains the complete per-lane comparison.
COEFFICIENT_SHA256_FIXTURES: tuple[tuple[str, str], ...] = (
    ("base-j0-i0", "5e6743d0e910217e517a7e7c11f80fa1ba7b0203ecb6292c66005dd2b7479cb4"),
    ("base-j0-i1", "02051d7f370c1e93e272bd73bfdaa55820cd53630440670816048585d514bbc1"),
    ("base-j0-i2", "558a37cc6ea9b093db7fd90b6ef94e5832c8159c03feeecd818cae58eb8ff48d"),
    ("base-j0-i3", "d00c663447ce10dc258695e93a66658c4dc0bba670c72ce13f418d8a7bafa64e"),
    ("base-j1-i0", "2704c24083a6247eb819d3fc40b54fc75b9599e19eb3c2bdc2f30bdd4bd8203c"),
    ("base-j1-i1", "96720e48cac7f3a10c898fb6b939c7cf4a15f706d54ca71dcca7623228127528"),
    ("base-j1-i2", "92b53d845832525bb865ffc3dcf99f48aafd677ec2789b0212b09e186aa1d89c"),
    ("base-j1-i3", "fcfc4159d84c326e50b9bee7895d19c90f6baa7ad88dae44f3715d1c662a396a"),
    ("base-j2-i0", "e8a5fab9926f4cbefe33aae7d56b47657a965a8e958db8768d5b9db58067bd4b"),
    ("base-j2-i1", "6a3bb04ad030849ac9ba4b0b04405aad19dfbcfba2b16ed14c1e39602186db56"),
    ("base-j2-i2", "62a994b9b6f031910994dd7464ae8752fb75dd300af87f87f0b8a9fb41565eda"),
    ("base-j2-i3", "cbdfa858b2e3e7419e3b9fb8930231fa2c6f9ce3f29a0abf8ffbb1c2bbd6bcab"),
    ("base-j3-i0", "39d27ac326e36e9c07ec3443944d722a5a708ca4941a7316585d89b0a8fc66fa"),
    ("base-j3-i1", "c74579deacc189f8f9f55815d02f32da80125f7e1ddb33ae24b6f84a42a879af"),
    ("base-j3-i2", "d17b32e8d4c4dd48f357facaf0dbe2dbbc73c3a944d3e4d8eb47b3bfae2d3206"),
    ("base-j3-i3", "59fef4dbaf69278b80fb823b184f7068b88abbc1a8044fdb37dbabc7fd71d6e3"),
    ("varied-00", "29939838a9f6f7569bbeeb101faa1e8139faa19319182ddb2d588061364e2031"),
    ("varied-01", "f698327bf3f4d8f4469be02fc5685335cbe704f599151dfc4cb9f5d7a007ca97"),
    ("varied-02", "dacb2820bc453bd763fc7b3ffc523440f9cd2ceac62bf7d46a27d7f845c3f9b9"),
    ("varied-03", "4e218e77bcc1ecff41e5efd7a23bce51a575ed8c6bacdc0ccf053b0cd8086eca"),
    ("varied-04", "d3e11796aba428b66d25a0a7d3faca9ed1ce5fe64259eb3a19d498c04d12afb9"),
    ("varied-05", "300885d1581b8e7717225d77605ca4b01a67d0cb3de583b9735b589d501e7ec7"),
    ("varied-06", "5dfe874ec2fbe5b6cac00b63cf1eda9ab87631c1bfb0f2efb46792a7a2e1f067"),
    ("varied-07", "6923ab0c757713a1e8de341b532927b707a1d408cfc1a265c0a5ea9a5d40d5d8"),
    ("varied-08", "ca38bcaea471b8e3167241bc16a1d93a9a50737a10beb55b1290a1332d88c6be"),
    ("varied-09", "b086b71fd4e006aa3627be0623ae4b4c8a3921b65399a27cdcd77165864b566d"),
    ("varied-10", "79076ad8eb3368985f5822b4e4270da1e0530454e406c431ee08731a28757139"),
    ("varied-11", "bc0596393bd2d0ac21042c1f04675830383da9fd4f868ade3deca7a9debf811b"),
    ("varied-12", "bcc1145e713ad74b57fd6fae067d8da70e28e80ea497a3ea9ccf78b98ba283ec"),
    ("varied-13", "7bf6987df6dcf9a67218868045f3d1d6feba85e2a9466896c17cd0859b05246e"),
    ("varied-14", "9bceeb2ee851a536f54b6f0a0bc1f67f7cbf614967dcde8d5b6e1a7218bc5eb9"),
    ("varied-15", "3b7b7117e6ef9c1d52c9f3168dc977e7e63e675f27004dd41030ff06fa048e5c"),
    (
        "boundary-alternating-00-ff",
        "7a6dde5d6356eba98bdb6cad24aa840741c2709b7d820855cf032108b8009fd8",
    ),
)
FINGERPRINT_BY_LABEL = dict(COEFFICIENT_SHA256_FIXTURES)
assert len(FINGERPRINT_BY_LABEL) == len(PRE_SILICON_CORPUS) == 33

DR1_CORPUS_SERIALIZATION_VERSION = b"phoenix-npu-pqc/dr1-corpus-v1\x00"
DR1_CORPUS_SHA256 = "6f6ff6ef59666417492605b3aeded74c299ec053847147a38803b0948b1ee459"


def serialize_pre_silicon_corpus(
    corpus: tuple[CorpusCase, ...] = PRE_SILICON_CORPUS,
) -> bytes:
    """Return the canonical bytes for the DR1 requests and expected fingerprints.

    This is deliberately a compact binary serialization rather than a repr:
    field boundaries, integer byte order, corpus ordering, and the expected
    per-case coefficient fingerprint are all part of the identity.
    """

    chunks = [DR1_CORPUS_SERIALIZATION_VERSION, len(corpus).to_bytes(2, "little")]
    for case in corpus:
        label = case.label.encode("utf-8")
        fingerprint = FINGERPRINT_BY_LABEL.get(case.label)
        if fingerprint is None:
            raise AssertionError(f"missing frozen fingerprint for {case.label!r}")
        fingerprint_bytes = fingerprint.encode("ascii")
        if len(label) > 0xFFFF or len(fingerprint_bytes) > 0xFF:
            raise AssertionError(
                f"unserializable corpus label or fingerprint: {case.label!r}"
            )
        chunks.extend(
            (
                len(label).to_bytes(2, "little"),
                label,
                case.rho,
                bytes((case.j, case.i)),
                case.request_id.to_bytes(4, "little"),
                len(fingerprint_bytes).to_bytes(1, "little"),
                fingerprint_bytes,
            )
        )
    return b"".join(chunks)


def pre_silicon_corpus_sha256(
    corpus: tuple[CorpusCase, ...] = PRE_SILICON_CORPUS,
) -> str:
    """Return the immutable SHA-256 identity of the canonical corpus bytes."""

    return hashlib.sha256(serialize_pre_silicon_corpus(corpus)).hexdigest()


def _coefficient_digest(coefficients: tuple[int, ...] | list[int]) -> str:
    return hashlib.sha256(struct.pack("<256i", *coefficients)).hexdigest()


class DR1ReferenceTests(unittest.TestCase):
    def test_independent_reference_handles_all_mldsa44_coordinates_exactly(
        self,
    ) -> None:
        rho = bytes(range(32))
        results = [
            expanda_rejntt_reference(rho, j, i) for j in range(4) for i in range(4)
        ]
        self.assertTrue(all(not result.limit_exceeded for result in results))
        self.assertTrue(all(result.accepted_count == 256 for result in results))
        self.assertTrue(all(result.blocks_executed == 8 for result in results))
        self.assertEqual(
            results[2].coefficients[:8],
            (6311339, 6469688, 7194785, 8319425, 8250096, 1900147, 4250255, 1906562),
        )

    def test_frozen_test_only_fingerprints_cover_the_33_case_corpus(self) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                result = expanda_rejntt_reference(case.rho, case.j, case.i)
                self.assertFalse(result.limit_exceeded)
                self.assertEqual(
                    _coefficient_digest(result.coefficients),
                    FINGERPRINT_BY_LABEL[case.label],
                )

    def test_canonical_serialized_corpus_has_immutable_identity(self) -> None:
        self.assertEqual(len(PRE_SILICON_CORPUS), 33)
        self.assertEqual(len(serialize_pre_silicon_corpus()), 3827)
        self.assertEqual(
            pre_silicon_corpus_sha256(),
            "6f6ff6ef59666417492605b3aeded74c299ec053847147a38803b0948b1ee459",
        )
        self.assertEqual(pre_silicon_corpus_sha256(), DR1_CORPUS_SHA256)

    def test_four_block_reference_specialization_is_an_explicit_limit_failure(
        self,
    ) -> None:
        result = expanda_rejntt_reference(bytes(range(32)), 0, 0, max_blocks=4)
        self.assertTrue(result.limit_exceeded)
        self.assertEqual(
            (result.coefficients, result.accepted_count, result.blocks_executed),
            ((), 0, 4),
        )


class DR1AbiTests(unittest.TestCase):
    def test_descriptor_layout_is_exact(self) -> None:
        descriptor = abi.build_descriptor(3, 1, 0x78563412)
        self.assertEqual(len(descriptor), 16)
        self.assertEqual(
            descriptor,
            bytes((1, 0x11, 0x44, 0, 3, 1, 8, 0, 0x12, 0x34, 0x56, 0x78, 0, 0, 0, 0)),
        )

    def test_malformed_inputs_fail_before_iron_loading(self) -> None:
        original = graph._load_iron
        graph._load_iron = lambda: (_ for _ in ()).throw(AssertionError("IRON loaded"))
        try:
            with self.assertRaises(abi.Dr1AbiError):
                graph.run_mldsa44_expanda_rejntt(b"x" * 31, 0, 0, 0)
            with self.assertRaises(abi.Dr1AbiError):
                graph.run_mldsa44_expanda_rejntt(b"x" * 32, 4, 0, 0)
            with self.assertRaises(TypeError):
                graph.run_mldsa44_expanda_rejntt(b"x" * 32, True, 0, 0)
            with self.assertRaises(abi.Dr1AbiError):
                graph.run_mldsa44_expanda_rejntt(b"x" * 32, 0, 0, 1 << 32)
        finally:
            graph._load_iron = original

    def test_terminal_sentinel_and_error_results_fail_closed(self) -> None:
        with self.assertRaises(abi.Dr1AbiError):
            abi.parse_result(abi.result_sentinel(), 7)
        error = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHBB", error, 0, abi.RESULT_MAGIC, 7, abi.STATUS_LIMIT_EXCEEDED, 0, 8, 0
        )
        with self.assertRaises(abi.Dr1OperationError):
            abi.parse_result(error, 7)
        struct.pack_into("<i", error, 16, 1)
        with self.assertRaises(abi.Dr1AbiError):
            abi.parse_result(error, 7)

    def test_success_result_requires_full_header_and_canonical_lanes(self) -> None:
        result = bytearray(abi.RESULT_BYTES)
        struct.pack_into(
            "<IIIHBB", result, 0, abi.RESULT_MAGIC, 9, abi.STATUS_OK, 256, 8, 0
        )
        for lane in range(256):
            struct.pack_into("<i", result, 16 + 4 * lane, lane)
        parsed = abi.parse_result(result, 9)
        self.assertEqual(parsed[:3], [0, 1, 2])
        struct.pack_into("<i", result, 16, abi.Q)
        with self.assertRaises(abi.Dr1AbiError):
            abi.parse_result(result, 9)


@unittest.skipUnless(shutil.which("g++"), "requires g++ host compiler")
class DR1ProductionKernelHarnessTests(unittest.TestCase):
    """Compile production C++ and compare complete streams/results to hashlib."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="dr1-kernel-test-")
        library = Path(cls._directory.name) / "dr1_kernels.so"
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
                "-I",
                str(KERNELS),
                str(KERNELS / "dr1_shake128_service.cc"),
                str(KERNELS / "dr1_mldsa44_rejntt.cc"),
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

    def _produce_blocks(
        self, rho: bytes, j: int, i: int, request_id: int
    ) -> list[bytes]:
        descriptor = abi.build_descriptor(j, i, request_id)
        blocks: list[bytes] = []
        for block in range(abi.BLOCK_CAP):
            output = self.block_type()
            self.library.dr1_shake128_emit_next(
                self.rho_type.from_buffer_copy(rho),
                self.descriptor_type.from_buffer_copy(descriptor),
                output,
            )
            blocks.append(bytes(output))
        return blocks

    def _consume_all_blocks(self, blocks: list[bytes | bytearray]) -> bytes:
        """Call one sampler entry point eight times; corruption never short-circuits."""
        self.assertEqual(len(blocks), abi.BLOCK_CAP)
        result = self.result_type()
        for block in range(abi.BLOCK_CAP):
            self.library.dr1_rejntt_consume_next(
                self.block_type.from_buffer_copy(blocks[block]), result
            )
        return bytes(result)

    def _run_kernel(self, case: CorpusCase) -> tuple[bytes, list[bytes]]:
        blocks = self._produce_blocks(case.rho, case.j, case.i, case.request_id)
        return self._consume_all_blocks(blocks), blocks

    def _assert_bad_descriptor_terminal(self, raw: bytes, request_id: int) -> None:
        with self.assertRaises(abi.Dr1OperationError):
            abi.parse_result(raw, request_id)
        header = struct.unpack_from("<IIIHBB", raw)
        self.assertEqual(
            header,
            (
                abi.RESULT_MAGIC,
                request_id,
                abi.STATUS_BAD_DESCRIPTOR,
                0,
                abi.BLOCK_CAP,
                0,
            ),
        )
        self.assertEqual(raw[16:], b"\x00" * 1024)

    def test_full_33_case_compiled_production_corpus_matches_hashlib_exactly(
        self,
    ) -> None:
        for case in PRE_SILICON_CORPUS:
            with self.subTest(case=case.label):
                raw, blocks = self._run_kernel(case)
                stream = shake128_stream_reference(case.rho, case.j, case.i)
                expected = expanda_rejntt_reference(case.rho, case.j, case.i)
                self.assertFalse(expected.limit_exceeded)
                self.assertEqual(b"".join(token[12:] for token in blocks), stream)
                actual = abi.parse_result(raw, case.request_id)
                self.assertEqual(len(actual), abi.N)
                self.assertEqual(actual, list(expected.coefficients))
                self.assertEqual(
                    _coefficient_digest(actual), FINGERPRINT_BY_LABEL[case.label]
                )

    def test_repeated_requests_in_one_compiled_process_reset_producer_and_sampler_state(
        self,
    ) -> None:
        cases = (PRE_SILICON_CORPUS[0], PRE_SILICON_CORPUS[20], PRE_SILICON_CORPUS[-1])
        outputs: list[bytes] = []
        for case in cases:
            with self.subTest(case=case.label):
                raw, blocks = self._run_kernel(case)
                self.assertEqual(
                    b"".join(token[12:] for token in blocks),
                    shake128_stream_reference(case.rho, case.j, case.i),
                )
                actual = abi.parse_result(raw, case.request_id)
                self.assertEqual(
                    actual,
                    list(
                        expanda_rejntt_reference(case.rho, case.j, case.i).coefficients
                    ),
                )
                outputs.append(raw[16:])
        self.assertEqual(len({case.request_id for case in cases}), len(cases))
        self.assertEqual(len(set(outputs)), len(outputs))

    def test_new_request_id_resets_interrupted_host_harness_state(self) -> None:
        """Exercise the defensive new-request boundary; production schedules eight calls."""
        abandoned = PRE_SILICON_CORPUS[1]
        replacement = PRE_SILICON_CORPUS[22]
        descriptor = abi.build_descriptor(
            abandoned.j, abandoned.i, abandoned.request_id
        )
        partial_blocks: list[bytes] = []
        for _ in range(3):
            output = self.block_type()
            self.library.dr1_shake128_emit_next(
                self.rho_type.from_buffer_copy(abandoned.rho),
                self.descriptor_type.from_buffer_copy(descriptor),
                output,
            )
            partial_blocks.append(bytes(output))
        partial_result = self.result_type()
        for block in partial_blocks:
            self.library.dr1_rejntt_consume_next(
                self.block_type.from_buffer_copy(block), partial_result
            )

        raw, blocks = self._run_kernel(replacement)
        self.assertEqual(
            b"".join(token[12:] for token in blocks),
            shake128_stream_reference(replacement.rho, replacement.j, replacement.i),
        )
        self.assertEqual(
            abi.parse_result(raw, replacement.request_id),
            list(
                expanda_rejntt_reference(
                    replacement.rho, replacement.j, replacement.i
                ).coefficients
            ),
        )

    def test_sampler_token_corruption_drains_all_eight_and_returns_bad_descriptor(
        self,
    ) -> None:
        case = PRE_SILICON_CORPUS[5]
        corruptions = (
            ("wrong_sequence", 3, 4, "<H", 99),
            ("wrong_echoed_request_id", 4, 0, "<I", case.request_id ^ 0x01020304),
            ("unexpected_producer_status", 5, 8, "<I", 99),
            ("bytes_valid_not_168", 6, 6, "<H", 167),
        )
        for label, block_index, offset, format_string, value in corruptions:
            with self.subTest(corruption=label):
                blocks = [
                    bytearray(token)
                    for token in self._produce_blocks(
                        case.rho, case.j, case.i, case.request_id
                    )
                ]
                struct.pack_into(format_string, blocks[block_index], offset, value)
                raw = self._consume_all_blocks(blocks)
                self._assert_bad_descriptor_terminal(raw, case.request_id)

    def test_success_freezes_first_256_accepts_but_consumes_all_eight_blocks(
        self,
    ) -> None:
        case = PRE_SILICON_CORPUS[17]
        raw, blocks = self._run_kernel(case)
        stream = shake128_stream_reference(case.rho, case.j, case.i)
        all_accepted = accepted_candidates_from_stream(stream)
        self.assertEqual(len(blocks), abi.BLOCK_CAP)
        self.assertEqual(b"".join(token[12:] for token in blocks), stream)
        self.assertGreater(len(all_accepted), abi.N)
        self.assertEqual(
            abi.parse_result(raw, case.request_id), list(all_accepted[: abi.N])
        )

    def test_bad_descriptor_still_drains_eight_error_tokens_and_returns_zero_payload(
        self,
    ) -> None:
        case = PRE_SILICON_CORPUS[0]
        descriptor = bytearray(abi.build_descriptor(case.j, case.i, case.request_id))
        descriptor[6] = 7
        blocks: list[bytes] = []
        for block in range(abi.BLOCK_CAP):
            output = self.block_type()
            self.library.dr1_shake128_emit_next(
                self.rho_type.from_buffer_copy(case.rho),
                self.descriptor_type.from_buffer_copy(descriptor),
                output,
            )
            blocks.append(bytes(output))
        self.assertEqual(
            [struct.unpack_from("<IHHI", token) for token in blocks],
            [
                (case.request_id, sequence, 0, abi.STATUS_BAD_DESCRIPTOR)
                for sequence in range(abi.BLOCK_CAP)
            ],
        )
        self._assert_bad_descriptor_terminal(
            self._consume_all_blocks(blocks), case.request_id
        )


if __name__ == "__main__":
    unittest.main()
