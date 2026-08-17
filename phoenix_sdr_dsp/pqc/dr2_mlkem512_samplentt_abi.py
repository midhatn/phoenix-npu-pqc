"""Fixed fail-closed ABI for the DR2a ML-KEM-512 matrix SampleNTT graph.

DR2a deliberately produces one public ML-KEM-512 matrix polynomial only.  It
does not expose a generic SHAKE service, a partial polynomial, or any host
fallback.  Host validation completes before native IRON/XRT loading.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

N = 256
Q = 3329
RHO_BYTES = 32
DESCRIPTOR_BYTES = 16
XOF_DATA_BYTES = 168
XOF_BLOCK_BYTES = 12 + XOF_DATA_BYTES
RESULT_HEADER_BYTES = 16
RESULT_BYTES = RESULT_HEADER_BYTES + 2 * N

ABI_VERSION = 1
OPCODE_MLKEM512_SAMPLENTT = 0x21
PARAMETER_MLKEM512 = 0x52
BLOCK_CAP = 5
FIPS203_CANDIDATE_ITERATION_CAP = 280

RESULT_MAGIC = 0x4452324D  # Bytes are b"M2RD" in the little-endian buffer.
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
VALID_STATUSES = frozenset((STATUS_OK, STATUS_LIMIT_EXCEEDED, STATUS_BAD_DESCRIPTOR))

OUTPUT_SENTINEL = -1


class Dr2aAbiError(ValueError):
    """A host request or terminal byte buffer violates the fixed DR2a ABI."""


class Dr2aOperationError(RuntimeError):
    """The device returned a valid DR2a terminal error result."""


def _require_python_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int; got {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise Dr2aAbiError(f"{name}={value} is outside [{minimum}, {maximum}]")
    return value


def validate_rho(rho: bytes | bytearray | memoryview) -> bytes:
    """Return immutable, exact-length ML-KEM rho without loading native code."""
    if not isinstance(rho, (bytes, bytearray, memoryview)):
        raise TypeError("rho must be bytes-like and exactly 32 bytes")
    checked = bytes(rho)
    if len(checked) != RHO_BYTES:
        raise Dr2aAbiError(
            f"rho must contain exactly {RHO_BYTES} bytes; got {len(checked)}"
        )
    return checked


def validate_coordinates(j: int, i: int) -> tuple[int, int]:
    """Validate ML-KEM-512 column/row coordinates in FIPS wire order."""
    return (
        _require_python_int("j", j, 0, 1),
        _require_python_int("i", i, 0, 1),
    )


def validate_request_id(request_id: int) -> int:
    """Validate the opaque little-endian u32 request identifier."""
    return _require_python_int("request_id", request_id, 0, (1 << 32) - 1)


def build_descriptor(j: int, i: int, request_id: int) -> bytes:
    """Build the exact 16-byte DR2a descriptor after strict host validation."""
    checked_j, checked_i = validate_coordinates(j, i)
    checked_request_id = validate_request_id(request_id)
    return struct.pack(
        "<BBBBBBBBI4s",
        ABI_VERSION,
        OPCODE_MLKEM512_SAMPLENTT,
        PARAMETER_MLKEM512,
        0,
        checked_j,
        checked_i,
        BLOCK_CAP,
        0,
        checked_request_id,
        b"\x00" * 4,
    )


def validate_request(
    rho: bytes | bytearray | memoryview, j: int, i: int, request_id: int
) -> tuple[bytes, bytes]:
    """Validate public inputs and return canonical rho/descriptor bytes."""
    return validate_rho(rho), build_descriptor(j, i, request_id)


def result_sentinel() -> bytes:
    """Create an invalid result with a visibly unwritten coefficient payload."""
    record = bytearray(RESULT_BYTES)
    record[RESULT_HEADER_BYTES:] = bytes((0xFF,)) * (RESULT_BYTES - RESULT_HEADER_BYTES)
    return bytes(record)


def _as_result_bytes(result: bytes | bytearray | memoryview | Sequence[int]) -> bytes:
    if isinstance(result, (bytes, bytearray, memoryview)):
        raw = bytes(result)
    else:
        try:
            raw = bytes(result)
        except (TypeError, ValueError) as exc:
            raise TypeError("terminal result must be bytes-like or uint8 sequence") from exc
    if len(raw) != RESULT_BYTES:
        raise Dr2aAbiError(
            f"terminal result must contain exactly {RESULT_BYTES} bytes; got {len(raw)}"
        )
    return raw


def parse_result(
    result: bytes | bytearray | memoryview | Sequence[int], request_id: int
) -> list[int]:
    """Validate the terminal ABI and return only a complete sampled polynomial."""
    expected_request_id = validate_request_id(request_id)
    raw = _as_result_bytes(result)
    magic, echoed_request_id, status = struct.unpack_from("<III", raw, 0)
    accepted = struct.unpack_from("<H", raw, 12)[0]
    blocks_executed = raw[14]
    reserved = raw[15]
    coefficients = list(struct.unpack_from("<256h", raw, RESULT_HEADER_BYTES))

    if magic != RESULT_MAGIC:
        raise Dr2aAbiError("terminal result magic was not replaced by the device")
    if echoed_request_id != expected_request_id:
        raise Dr2aAbiError("terminal result request_id does not echo the request")
    if status not in VALID_STATUSES:
        raise Dr2aAbiError(f"terminal result has unknown status {status}")
    if blocks_executed != BLOCK_CAP:
        raise Dr2aAbiError(
            f"terminal result blocks_executed={blocks_executed}; expected {BLOCK_CAP}"
        )
    if reserved != 0:
        raise Dr2aAbiError("terminal result reserved byte is nonzero")

    if status == STATUS_OK:
        if accepted != N:
            raise Dr2aAbiError(
                f"successful terminal result accepted_count={accepted}; expected {N}"
            )
        if any(value < 0 or value >= Q for value in coefficients):
            raise Dr2aAbiError("successful terminal result contains non-canonical lanes")
        return coefficients

    if accepted != 0:
        raise Dr2aAbiError("terminal error result must have accepted_count=0")
    if any(coefficients):
        raise Dr2aAbiError(
            "terminal error result must overwrite every coefficient lane with zero"
        )
    status_name = (
        "LIMIT_EXCEEDED" if status == STATUS_LIMIT_EXCEEDED else "BAD_DESCRIPTOR"
    )
    raise Dr2aOperationError(
        f"DR2a device graph returned {status_name}; no host fallback is available"
    )


__all__ = [
    "ABI_VERSION",
    "BLOCK_CAP",
    "DESCRIPTOR_BYTES",
    "FIPS203_CANDIDATE_ITERATION_CAP",
    "OPCODE_MLKEM512_SAMPLENTT",
    "OUTPUT_SENTINEL",
    "PARAMETER_MLKEM512",
    "RESULT_BYTES",
    "RESULT_MAGIC",
    "RHO_BYTES",
    "STATUS_BAD_DESCRIPTOR",
    "STATUS_LIMIT_EXCEEDED",
    "STATUS_OK",
    "XOF_BLOCK_BYTES",
    "XOF_DATA_BYTES",
    "Dr2aAbiError",
    "Dr2aOperationError",
    "N",
    "Q",
    "build_descriptor",
    "parse_result",
    "result_sentinel",
    "validate_coordinates",
    "validate_request",
    "validate_request_id",
    "validate_rho",
]
