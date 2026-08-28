"""Fixed fail-closed ABI for the complete resident ML-KEM-512 K-PKE.Encrypt.

DR3 accepts a public key ekPKE (800 B), plaintext message m (32 B),
encryption randomness r (32 B), and an immutable request descriptor.
The device computes all encryption transformations on AIE2 hardware tiles
and returns one terminal record containing the byte-exact ciphertext c (768 B).
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence

N = 256
Q = 3329
K = 2
ETA1 = 3
ETA2 = 2
DU = 10
DV = 4

RHO_BYTES = 32
M_BYTES = 32
R_BYTES = 32
POLY_ENCODED_12_BYTES = 384
EK_PKE_BYTES = K * POLY_ENCODED_12_BYTES + RHO_BYTES  # 800 B
REQUEST_PAYLOAD_BYTES = EK_PKE_BYTES + M_BYTES + R_BYTES  # 864 B
DESCRIPTOR_BYTES = 16

POLY_COMPRESSED_10_BYTES = 320
POLY_COMPRESSED_4_BYTES = 128
CIPHERTEXT_BYTES = K * POLY_COMPRESSED_10_BYTES + POLY_COMPRESSED_4_BYTES  # 768 B

RESULT_HEADER_BYTES = 20
RESULT_BYTES = RESULT_HEADER_BYTES + CIPHERTEXT_BYTES  # 788 B

ABI_VERSION = 1
OPCODE_MLKEM512_KPKE_ENCRYPT = 0x31
PARAMETER_MLKEM512 = 0x52
SAMPLE_NTT_BLOCK_CAP = 5
RESULT_MAGIC = 0x4433524D  # Little-endian bytes: b"MR3D".
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3
VALID_STATUSES = frozenset(
    (STATUS_OK, STATUS_LIMIT_EXCEEDED, STATUS_BAD_DESCRIPTOR, STATUS_BAD_TOKEN)
)


class Dr3AbiError(ValueError):
    """A public DR3 request or terminal record violates the fixed ABI."""


class Dr3OperationError(RuntimeError):
    """The resident graph returned a valid fixed-zero-payload terminal error."""


def _require_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int; got {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise Dr3AbiError(f"{name}={value} is outside [{minimum}, {maximum}]")
    return value


def validate_request_id(request_id: int) -> int:
    return _require_int("request_id", request_id, 0, (1 << 32) - 1)


def build_descriptor(request_id: int) -> bytes:
    """Build the v1 descriptor for ML-KEM-512 K-PKE.Encrypt."""
    return struct.pack(
        "<BBBBBBBBI4s",
        ABI_VERSION,
        OPCODE_MLKEM512_KPKE_ENCRYPT,
        PARAMETER_MLKEM512,
        0,
        K,
        ETA1,
        ETA2,
        SAMPLE_NTT_BLOCK_CAP,
        validate_request_id(request_id),
        b"\x00" * 4,
    )


def pack_request_payload(ek: bytes, m: bytes, r: bytes) -> bytes:
    """Pack ek (800 B), m (32 B), and r (32 B) into one 864-byte payload."""
    if len(ek) != EK_PKE_BYTES:
        raise Dr3AbiError(f"ek must be {EK_PKE_BYTES} bytes, got {len(ek)}")
    if len(m) != M_BYTES:
        raise Dr3AbiError(f"m must be {M_BYTES} bytes, got {len(m)}")
    if len(r) != R_BYTES:
        raise Dr3AbiError(f"r must be {R_BYTES} bytes, got {len(r)}")
    return bytes(ek) + bytes(m) + bytes(r)


def validate_request(
    ek: bytes, m: bytes, r: bytes, request_id: int
) -> tuple[bytes, bytes]:
    return build_descriptor(request_id), pack_request_payload(ek, m, r)


def unpack_result(
    raw: bytes | bytearray | memoryview, *, expected_request_id: int | None = None
) -> bytes:
    """Unpack terminal result record, verifying magic, CRC32, and status."""
    buf = bytes(raw)
    if len(buf) < RESULT_BYTES:
        raise Dr3AbiError(f"result too short: expected >= {RESULT_BYTES}, got {len(buf)}")

    magic, request_id, status, c_len, crc32 = struct.unpack_from("<IIIII", buf, 0)
    if magic != RESULT_MAGIC:
        raise Dr3AbiError(f"bad magic: {hex(magic)}, expected {hex(RESULT_MAGIC)}")

    if expected_request_id is not None and request_id != expected_request_id:
        raise Dr3AbiError(f"request_id mismatch: expected {expected_request_id}, got {request_id}")

    if status != STATUS_OK:
        raise Dr3OperationError(f"device execution failed with status {status}")

    if c_len != CIPHERTEXT_BYTES:
        raise Dr3AbiError(f"bad ciphertext length: expected {CIPHERTEXT_BYTES}, got {c_len}")

    ciphertext = buf[RESULT_HEADER_BYTES : RESULT_HEADER_BYTES + CIPHERTEXT_BYTES]
    computed_crc = zlib.crc32(ciphertext)
    if computed_crc != crc32:
        raise Dr3AbiError(f"CRC32 mismatch: expected {hex(crc32)}, computed {hex(computed_crc)}")

    return ciphertext
