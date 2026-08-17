"""Fixed fail-closed ABI for one resident ML-KEM-512 K-PKE.KeyGen row.

The public API accepts ``rho`` and ``sigma`` separately, then packs them as one
fixed 64-byte seed ingress alongside a strict descriptor/request ID.  A successful result is one canonical ``t_hat`` row;
matrix, PRF, CBD, NTT, and multiplication intermediates never form a graph
terminal output.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

N = 256
Q = 3329
RHO_BYTES = 32
SIGMA_BYTES = 32
SEEDS_BYTES = RHO_BYTES + SIGMA_BYTES
DESCRIPTOR_BYTES = 16
SAMPLE_NTT_BLOCK_CAP = 5
ETA1 = 3
INTERNAL_POLYNOMIALS = 5  # A[row,0], A[row,1], s_hat[0], s_hat[1], e_hat[row]
INTERNAL_TOKEN_BYTES = 16 + INTERNAL_POLYNOMIALS * 2 * N
RESULT_HEADER_BYTES = 16
RESULT_BYTES = RESULT_HEADER_BYTES + 2 * N

ABI_VERSION = 1
OPCODE_MLKEM512_KEYGEN_ROW = 0x23
PARAMETER_MLKEM512 = 0x52
RESULT_MAGIC = 0x4332524D  # Little-endian bytes: b"MR2C".
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3
VALID_STATUSES = frozenset(
    (STATUS_OK, STATUS_LIMIT_EXCEEDED, STATUS_BAD_DESCRIPTOR, STATUS_BAD_TOKEN)
)


class Dr2cAbiError(ValueError):
    """A public DR2c request or terminal result violated the fixed ABI."""


class Dr2cOperationError(RuntimeError):
    """The resident graph returned a valid zero-payload terminal error."""


def _require_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int; got {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise Dr2cAbiError(f"{name}={value} is outside [{minimum}, {maximum}]")
    return value


def _validate_seed(name: str, seed: bytes | bytearray | memoryview) -> bytes:
    if not isinstance(seed, (bytes, bytearray, memoryview)):
        raise TypeError(f"{name} must be bytes-like and exactly 32 bytes")
    checked = bytes(seed)
    if len(checked) != 32:
        raise Dr2cAbiError(f"{name} must contain exactly 32 bytes; got {len(checked)}")
    return checked


def validate_rho(rho: bytes | bytearray | memoryview) -> bytes:
    """Validate the public matrix seed before native runtime loading."""
    return _validate_seed("rho", rho)


def validate_sigma(sigma: bytes | bytearray | memoryview) -> bytes:
    """Validate the private noise seed before native runtime loading."""
    return _validate_seed("sigma", sigma)


def validate_row_index(row_index: int) -> int:
    """ML-KEM-512 K-PKE.KeyGen contains exactly the two rows 0 and 1."""
    return _require_int("row_index", row_index, 0, 1)


def validate_request_id(request_id: int) -> int:
    return _require_int("request_id", request_id, 0, (1 << 32) - 1)


def build_descriptor(row_index: int, request_id: int) -> bytes:
    """Build the immutable v1 descriptor after strict public validation."""
    return struct.pack(
        "<BBBBBBBBI4s",
        ABI_VERSION,
        OPCODE_MLKEM512_KEYGEN_ROW,
        PARAMETER_MLKEM512,
        0,
        validate_row_index(row_index),
        ETA1,
        SAMPLE_NTT_BLOCK_CAP,
        0,
        validate_request_id(request_id),
        b"\x00" * 4,
    )


def pack_seeds(
    rho: bytes | bytearray | memoryview, sigma: bytes | bytearray | memoryview
) -> bytes:
    """Validate and concatenate the two 32-byte KeyGen seeds for one DMA ingress."""
    return validate_rho(rho) + validate_sigma(sigma)


def validate_request(
    rho: bytes | bytearray | memoryview,
    sigma: bytes | bytearray | memoryview,
    row_index: int,
    request_id: int,
) -> tuple[bytes, bytes]:
    """Return immutable packed-seed and descriptor ingress records before IRON/XRT."""
    return pack_seeds(rho, sigma), build_descriptor(row_index, request_id)


def result_sentinel() -> bytes:
    record = bytearray(RESULT_BYTES)
    record[RESULT_HEADER_BYTES:] = b"\xff" * (RESULT_BYTES - RESULT_HEADER_BYTES)
    return bytes(record)


def _result_bytes(result: bytes | bytearray | memoryview | Sequence[int]) -> bytes:
    try:
        raw = bytes(result)
    except (TypeError, ValueError) as exc:
        raise TypeError("terminal result must be bytes-like or a uint8 sequence") from exc
    if len(raw) != RESULT_BYTES:
        raise Dr2cAbiError(
            f"terminal result must contain exactly {RESULT_BYTES} bytes; got {len(raw)}"
        )
    return raw


def parse_result(
    result: bytes | bytearray | memoryview | Sequence[int],
    row_index: int,
    request_id: int,
) -> list[int]:
    """Return a complete canonical KeyGen row, or reject it without fallback."""
    expected_row = validate_row_index(row_index)
    expected_request_id = validate_request_id(request_id)
    raw = _result_bytes(result)
    magic, echoed_request_id, status = struct.unpack_from("<III", raw, 0)
    coefficient_count = struct.unpack_from("<H", raw, 12)[0]
    echoed_row, reserved = raw[14], raw[15]
    coefficients = list(struct.unpack_from("<256h", raw, RESULT_HEADER_BYTES))
    if magic != RESULT_MAGIC:
        raise Dr2cAbiError("terminal result magic was not replaced by the device")
    if echoed_request_id != expected_request_id:
        raise Dr2cAbiError("terminal result request_id does not echo the request")
    if echoed_row != expected_row or reserved != 0:
        raise Dr2cAbiError("terminal result row index or reserved byte is invalid")
    if status not in VALID_STATUSES:
        raise Dr2cAbiError(f"terminal result has unknown status {status}")
    if status == STATUS_OK:
        if coefficient_count != N:
            raise Dr2cAbiError("successful terminal result lacks all 256 NTT lanes")
        if any(value < 0 or value >= Q for value in coefficients):
            raise Dr2cAbiError("successful terminal result contains non-canonical lanes")
        return coefficients
    if coefficient_count != 0 or any(coefficients):
        raise Dr2cAbiError("terminal error result must have a fixed zero payload")
    names = {
        STATUS_LIMIT_EXCEEDED: "LIMIT_EXCEEDED",
        STATUS_BAD_DESCRIPTOR: "BAD_DESCRIPTOR",
        STATUS_BAD_TOKEN: "BAD_TOKEN",
    }
    raise Dr2cOperationError(
        f"DR2c device graph returned {names[status]}; no host fallback is available"
    )


__all__ = [
    "ABI_VERSION",
    "DESCRIPTOR_BYTES",
    "ETA1",
    "INTERNAL_POLYNOMIALS",
    "INTERNAL_TOKEN_BYTES",
    "OPCODE_MLKEM512_KEYGEN_ROW",
    "PARAMETER_MLKEM512",
    "RESULT_BYTES",
    "RESULT_HEADER_BYTES",
    "RESULT_MAGIC",
    "RHO_BYTES",
    "SAMPLE_NTT_BLOCK_CAP",
    "SEEDS_BYTES",
    "SIGMA_BYTES",
    "STATUS_BAD_DESCRIPTOR",
    "STATUS_BAD_TOKEN",
    "STATUS_LIMIT_EXCEEDED",
    "STATUS_OK",
    "Dr2cAbiError",
    "Dr2cOperationError",
    "N",
    "Q",
    "build_descriptor",
    "pack_seeds",
    "parse_result",
    "result_sentinel",
    "validate_request",
    "validate_request_id",
    "validate_rho",
    "validate_row_index",
    "validate_sigma",
]
