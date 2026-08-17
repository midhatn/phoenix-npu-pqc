"""Fixed public ABI for DR1 ML-DSA-44 ExpandA/RejNTT.

DR1 deliberately exposes one polynomial request only.  It is not a generic
SHAKE service and it does not select any ML-DSA parameter set other than 44.
All validation in this module is host-only and completes before IRON/XRT is
loaded by :mod:`dr1_mldsa44_rejntt_graph`.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

N = 256
Q = 8_380_417
RHO_BYTES = 32
DESCRIPTOR_BYTES = 16
XOF_BLOCK_BYTES = 180
XOF_DATA_BYTES = 168
RESULT_BYTES = 1_040

ABI_VERSION = 1
OPCODE_EXPANDA_REJNTT = 0x11
PARAMETER_MLDSA44 = 0x44
BLOCK_CAP = 8

RESULT_MAGIC = 0x44523152  # Bytes are b"R1RD" in the little-endian buffer.
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
VALID_STATUSES = frozenset((STATUS_OK, STATUS_LIMIT_EXCEEDED, STATUS_BAD_DESCRIPTOR))

RESULT_HEADER_BYTES = 16
RESULT_COEFFICIENT_OFFSET = RESULT_HEADER_BYTES
OUTPUT_SENTINEL = -(1 << 31)


class Dr1AbiError(ValueError):
    """A host request or terminal byte buffer violates the fixed DR1 ABI."""


class Dr1OperationError(RuntimeError):
    """The device returned a valid DR1 terminal error result."""


def _require_python_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int; got {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise Dr1AbiError(f"{name}={value} is outside [{minimum}, {maximum}]")
    return value


def validate_rho(rho: bytes | bytearray | memoryview) -> bytes:
    """Return an immutable exact-length rho value without loading native code."""
    if not isinstance(rho, (bytes, bytearray, memoryview)):
        raise TypeError("rho must be bytes-like and exactly 32 bytes")
    checked = bytes(rho)
    if len(checked) != RHO_BYTES:
        raise Dr1AbiError(f"rho must contain exactly {RHO_BYTES} bytes; got {len(checked)}")
    return checked


def validate_coordinates(j: int, i: int) -> tuple[int, int]:
    """Validate the ML-DSA-44 column/row coordinates in wire order."""
    return (
        _require_python_int("j", j, 0, 3),
        _require_python_int("i", i, 0, 3),
    )


def validate_request_id(request_id: int) -> int:
    """Validate the opaque little-endian u32 request identifier."""
    return _require_python_int("request_id", request_id, 0, (1 << 32) - 1)


def build_descriptor(j: int, i: int, request_id: int) -> bytes:
    """Build the exact 16-byte v1 descriptor after strict host validation."""
    checked_j, checked_i = validate_coordinates(j, i)
    checked_request_id = validate_request_id(request_id)
    return struct.pack(
        "<BBBBBBBBI4s",
        ABI_VERSION,
        OPCODE_EXPANDA_REJNTT,
        PARAMETER_MLDSA44,
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
    """Validate every public input and return canonical rho/descriptor bytes."""
    return validate_rho(rho), build_descriptor(j, i, request_id)


def result_sentinel() -> bytes:
    """Create an invalid terminal record with every coefficient visibly unwritten."""
    record = bytearray(RESULT_BYTES)
    for lane in range(N):
        struct.pack_into("<i", record, RESULT_COEFFICIENT_OFFSET + 4 * lane, OUTPUT_SENTINEL)
    return bytes(record)


def _as_result_bytes(result: bytes | bytearray | memoryview | Sequence[int]) -> bytes:
    if isinstance(result, (bytes, bytearray, memoryview)):
        raw = bytes(result)
    else:
        # numpy uint8 tensors support this path while keeping ABI parsing local.
        try:
            raw = bytes(result)
        except (TypeError, ValueError) as exc:
            raise TypeError("terminal result must be bytes-like or uint8 sequence") from exc
    if len(raw) != RESULT_BYTES:
        raise Dr1AbiError(f"terminal result must contain exactly {RESULT_BYTES} bytes; got {len(raw)}")
    return raw


def parse_result(result: bytes | bytearray | memoryview | Sequence[int], request_id: int) -> list[int]:
    """Validate the entire terminal ABI and return only a successful polynomial.

    Terminal error statuses are fully checked (including their required zero
    payload) before :class:`Dr1OperationError` is raised.  This keeps malformed
    output distinct from a bounded on-device sampling failure.
    """
    expected_request_id = validate_request_id(request_id)
    raw = _as_result_bytes(result)
    magic, echoed_request_id, status = struct.unpack_from("<III", raw, 0)
    accepted = struct.unpack_from("<H", raw, 12)[0]
    blocks_executed = raw[14]
    reserved = raw[15]
    coefficients = list(struct.unpack_from("<256i", raw, RESULT_COEFFICIENT_OFFSET))

    if magic != RESULT_MAGIC:
        raise Dr1AbiError("terminal result magic was not replaced by the device")
    if echoed_request_id != expected_request_id:
        raise Dr1AbiError("terminal result request_id does not echo the request")
    if status not in VALID_STATUSES:
        raise Dr1AbiError(f"terminal result has unknown status {status}")
    if blocks_executed != BLOCK_CAP:
        raise Dr1AbiError(f"terminal result blocks_executed={blocks_executed}; expected {BLOCK_CAP}")
    if reserved != 0:
        raise Dr1AbiError("terminal result reserved byte is nonzero")

    if status == STATUS_OK:
        if accepted != N:
            raise Dr1AbiError(f"successful terminal result accepted_count={accepted}; expected {N}")
        if any(value < 0 or value >= Q for value in coefficients):
            raise Dr1AbiError("successful terminal result contains non-canonical coefficient lanes")
        return coefficients

    if accepted != 0:
        raise Dr1AbiError("terminal error result must have accepted_count=0")
    if any(coefficients):
        raise Dr1AbiError("terminal error result must overwrite every coefficient lane with zero")
    status_name = "LIMIT_EXCEEDED" if status == STATUS_LIMIT_EXCEEDED else "BAD_DESCRIPTOR"
    raise Dr1OperationError(f"DR1 device graph returned {status_name}; no host fallback is available")


__all__ = [
    "ABI_VERSION",
    "BLOCK_CAP",
    "DESCRIPTOR_BYTES",
    "OPCODE_EXPANDA_REJNTT",
    "OUTPUT_SENTINEL",
    "PARAMETER_MLDSA44",
    "RESULT_BYTES",
    "RESULT_MAGIC",
    "RHO_BYTES",
    "STATUS_BAD_DESCRIPTOR",
    "STATUS_LIMIT_EXCEEDED",
    "STATUS_OK",
    "XOF_BLOCK_BYTES",
    "XOF_DATA_BYTES",
    "Dr1AbiError",
    "Dr1OperationError",
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
