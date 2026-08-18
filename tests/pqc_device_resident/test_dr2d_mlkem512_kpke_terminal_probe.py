"""Host evidence for the diagnostic-only DR2d final-token terminal probe."""

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
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_abi as abi
from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_terminal_probe_graph as probe
from tests.pqc_device_resident.test_dr2d_mlkem512_kpke_keygen import (
    PRE_SILICON_CORPUS,
)

KERNELS = REPO_ROOT / "phoenix_sdr_dsp" / "pqc" / "kernels"


def _probe_lanes(polynomial: int, seed: int) -> tuple[int, ...]:
    lanes = []
    for lane in range(abi.N):
        ascending = 13 * lane + seed
        shallow = 11 * lane + 3 * seed
        if polynomial == 0:
            lanes.append(ascending)
        elif polynomial == 1:
            lanes.append(abi.Q - 1 - ascending)
        elif polynomial == 2:
            lanes.append(shallow)
        else:
            lanes.append(abi.Q - 1 - shallow)
    return tuple(lanes)


def _encode12(lanes: tuple[int, ...]) -> bytes:
    out = bytearray(abi.POLY_ENCODED_BYTES)
    for pair in range(abi.N // 2):
        first, second = lanes[2 * pair], lanes[2 * pair + 1]
        offset = 3 * pair
        out[offset] = first & 0xFF
        out[offset + 1] = (first >> 8) | ((second & 0x0F) << 4)
        out[offset + 2] = second >> 4
    return bytes(out)


def terminal_probe_expected(request_id: int) -> tuple[bytes, bytes]:
    """Independent expected normal terminal payload for the case-1 descriptor."""
    if request_id != probe.DIAGNOSTIC_CASE1_REQUEST_ID:
        raise ValueError("terminal probe has exactly one supported request ID")
    descriptor = abi.build_descriptor(request_id)
    seed = descriptor[8]
    rho = bytes(0xA5 ^ descriptor[8 + (index & 3)] ^ index for index in range(32))
    t0, t1, s0, s1 = tuple(_probe_lanes(polynomial, seed) for polynomial in range(4))
    return _encode12(t0) + _encode12(t1) + rho, _encode12(s0) + _encode12(s1)


def terminal_probe_expected_record(request_id: int) -> bytes:
    """Independently construct the exact normal 1,588-byte diagnostic record."""
    ek_pke, dk_pke = terminal_probe_expected(request_id)
    payload = ek_pke + dk_pke
    return (
        struct.pack(
            "<IIIHHI",
            abi.RESULT_MAGIC,
            request_id,
            abi.STATUS_OK,
            abi.EK_PKE_BYTES,
            abi.DK_PKE_BYTES,
            zlib.crc32(payload) & 0xFFFFFFFF,
        )
        + payload
    )


class DR2dTerminalProbeReferenceTests(unittest.TestCase):
    def test_case1_expected_payload_is_canonical_and_deterministic(self) -> None:
        ek_pke, dk_pke = terminal_probe_expected(probe.DIAGNOSTIC_CASE1_REQUEST_ID)
        self.assertEqual(
            (len(ek_pke), len(dk_pke)), (abi.EK_PKE_BYTES, abi.DK_PKE_BYTES)
        )
        self.assertEqual(
            terminal_probe_expected(probe.DIAGNOSTIC_CASE1_REQUEST_ID),
            (ek_pke, dk_pke),
        )
        for polynomial in range(4):
            self.assertTrue(all(lane < abi.Q for lane in _probe_lanes(polynomial, 1)))

    def test_case1_expected_record_pins_the_complete_normal_terminal_bytes(
        self,
    ) -> None:
        record = terminal_probe_expected_record(probe.DIAGNOSTIC_CASE1_REQUEST_ID)
        self.assertEqual(len(record), abi.RESULT_BYTES)
        self.assertEqual(
            hashlib.sha256(record).hexdigest(),
            "309c9dd65e843edb15bc67766aff8f37b302ef815a435813881d6908d567adb4",
        )
        self.assertEqual(
            abi.parse_result(record, probe.DIAGNOSTIC_CASE1_REQUEST_ID),
            terminal_probe_expected(probe.DIAGNOSTIC_CASE1_REQUEST_ID),
        )

    def test_encode12_keeps_even_lane_bits_8_through_11(self) -> None:
        lanes = (0x0CFF, 0x0CF2) + (0,) * (abi.N - 2)
        self.assertEqual(_encode12(lanes)[:3], bytes((0xFF, 0x2C, 0xCF)))

    def test_non_case1_request_fails_before_native_loading(self) -> None:
        original = probe._load_iron
        probe._load_iron = lambda: (_ for _ in ()).throw(AssertionError("IRON loaded"))
        try:
            with self.assertRaises(abi.Dr2dAbiError):
                probe.run_case1_terminal_probe(b"x" * abi.D_BYTES, 1)
        finally:
            probe._load_iron = original


@unittest.skipUnless(shutil.which("g++"), "requires g++ host compiler")
class DR2dTerminalProbeKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="dr2d-terminal-probe-")
        library = Path(cls._directory.name) / "dr2d_terminal_probe.so"
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
                str(KERNELS / "dr2d_mlkem512_kpke_keygen_terminal_probe.cc"),
                str(KERNELS / "dr2d_mlkem512_kpke_keygen_serialize.cc"),
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
        cls.final_type = ctypes.c_uint8 * abi.PRIVATE_TOKEN_BYTES
        cls.result_type = ctypes.c_uint8 * abi.RESULT_BYTES
        cls.library.dr2d_kpke_keygen_terminal_probe.argtypes = [
            ctypes.POINTER(cls.d_type),
            ctypes.POINTER(cls.descriptor_type),
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

    def test_known_case1_final_token_reaches_existing_serializer_exactly(self) -> None:
        case = PRE_SILICON_CORPUS[0]
        self.assertEqual(case.request_id, probe.DIAGNOSTIC_CASE1_REQUEST_ID)
        d = self.d_type.from_buffer_copy(case.d)
        descriptor = self.descriptor_type.from_buffer_copy(
            abi.build_descriptor(case.request_id)
        )
        final_token, result = self.final_type(), self.result_type()
        self.library.dr2d_kpke_keygen_terminal_probe(d, descriptor, final_token)
        snapshot = bytes(final_token)
        self.assertEqual(
            struct.unpack_from("<II", snapshot), (case.request_id, abi.STATUS_OK)
        )
        self.assertEqual(snapshot[8:32], b"\0" * 24)
        self.assertEqual(
            snapshot[1600:1604],
            bytes((0xFF, 0x0C, 0xF2, 0x0C)),
            "t_hat[1][0..1] must be one placement-constructed uint32 pair",
        )
        self.library.dr2d_kpke_keygen_serialize(final_token, result)
        self.assertEqual(bytes(result), terminal_probe_expected_record(case.request_id))
        self.assertEqual(
            abi.parse_result(bytes(result), case.request_id),
            terminal_probe_expected(case.request_id),
        )
        self.assertEqual(bytes(d), b"\0" * abi.D_BYTES)
        self.assertEqual(bytes(descriptor), b"\0" * abi.DESCRIPTOR_BYTES)
        self.assertEqual(bytes(final_token), b"\0" * abi.PRIVATE_TOKEN_BYTES)

    def test_probe_rejects_a_non_case1_descriptor_with_fixed_zero_error(self) -> None:
        d = self.d_type.from_buffer_copy(b"x" * abi.D_BYTES)
        descriptor = self.descriptor_type.from_buffer_copy(
            abi.build_descriptor(probe.DIAGNOSTIC_CASE1_REQUEST_ID + 1)
        )
        final_token, result = self.final_type(), self.result_type()
        self.library.dr2d_kpke_keygen_terminal_probe(d, descriptor, final_token)
        self.library.dr2d_kpke_keygen_serialize(final_token, result)
        with self.assertRaises(abi.Dr2dOperationError):
            abi.parse_result(bytes(result), probe.DIAGNOSTIC_CASE1_REQUEST_ID + 1)
        self.assertEqual(
            bytes(result)[abi.RESULT_HEADER_BYTES :],
            b"\0" * (abi.RESULT_BYTES - abi.RESULT_HEADER_BYTES),
        )

    def test_serializer_raw_byte_packing_keeps_even_lane_upper_nibble(self) -> None:
        case = PRE_SILICON_CORPUS[0]
        d = self.d_type.from_buffer_copy(case.d)
        descriptor = self.descriptor_type.from_buffer_copy(
            abi.build_descriptor(case.request_id)
        )
        final_token, result = self.final_type(), self.result_type()
        self.library.dr2d_kpke_keygen_terminal_probe(d, descriptor, final_token)
        struct.pack_into("<HH", final_token, 1088, 0x0CFF, 0x0CF2)
        self.library.dr2d_kpke_keygen_serialize(final_token, result)
        self.assertEqual(
            bytes(result)[abi.RESULT_HEADER_BYTES : abi.RESULT_HEADER_BYTES + 3],
            bytes((0xFF, 0x2C, 0xCF)),
        )
        self.assertEqual(bytes(final_token), b"\0" * abi.PRIVATE_TOKEN_BYTES)

    def test_existing_serializer_rejects_malformed_or_noncanonical_probe_tokens(
        self,
    ) -> None:
        case = PRE_SILICON_CORPUS[0]
        for corruption in ("reserved", "noncanonical"):
            with self.subTest(corruption=corruption):
                d = self.d_type.from_buffer_copy(case.d)
                descriptor = self.descriptor_type.from_buffer_copy(
                    abi.build_descriptor(case.request_id)
                )
                final_token, result = self.final_type(), self.result_type()
                self.library.dr2d_kpke_keygen_terminal_probe(d, descriptor, final_token)
                if corruption == "reserved":
                    final_token[8] = 1
                else:
                    struct.pack_into("<H", final_token, 1088, abi.Q)
                self.library.dr2d_kpke_keygen_serialize(final_token, result)
                with self.assertRaises(abi.Dr2dOperationError):
                    abi.parse_result(bytes(result), case.request_id)
                self.assertEqual(
                    bytes(result)[abi.RESULT_HEADER_BYTES :],
                    b"\0" * (abi.RESULT_BYTES - abi.RESULT_HEADER_BYTES),
                )
                self.assertEqual(bytes(final_token), b"\0" * abi.PRIVATE_TOKEN_BYTES)


if __name__ == "__main__":
    unittest.main()
