"""Fixed fail-closed ABI for DR2b ML-KEM-512 PRF/CBD/NTT noise sampling.

The only successful host result is one complete 256-lane NTT polynomial.  The
SHAKE256 PRF bytes and CBD-domain coefficients remain device-local.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

N = 256
Q = 3329
SIGMA_BYTES = 32
DESCRIPTOR_BYTES = 16
PRF_BYTES = 192
PRF_TOKEN_HEADER_BYTES = 16
PRF_TOKEN_BYTES = PRF_TOKEN_HEADER_BYTES + PRF_BYTES
RESULT_HEADER_BYTES = 16
RESULT_BYTES = RESULT_HEADER_BYTES + 2 * N

ABI_VERSION = 1
OPCODE_MLKEM512_NOISE_NTT = 0x22
PARAMETER_MLKEM512 = 0x52
ETA1 = 3
COUNTER_MIN = 0
COUNTER_MAX = 3  # K-PKE.KeyGen samples s[0], s[1], e[0], e[1] from sigma.
RESULT_MAGIC = 0x4232524D  # Little-endian bytes: b"MR2B".
STATUS_OK = 0
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3
VALID_STATUSES = frozenset((STATUS_OK, STATUS_BAD_DESCRIPTOR, STATUS_BAD_TOKEN))


class Dr2bAbiError(ValueError):
    """A public request or terminal result violates the fixed DR2b ABI."""


class Dr2bOperationError(RuntimeError):
    """The device returned a valid, fixed-zero-payload DR2b error."""


def _require_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int; got {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise Dr2bAbiError(f"{name}={value} is outside [{minimum}, {maximum}]")
    return value


def validate_sigma(sigma: bytes | bytearray | memoryview) -> bytes:
    if not isinstance(sigma, (bytes, bytearray, memoryview)):
        raise TypeError("sigma must be bytes-like and exactly 32 bytes")
    checked = bytes(sigma)
    if len(checked) != SIGMA_BYTES:
        raise Dr2bAbiError(
            f"sigma must contain exactly {SIGMA_BYTES} bytes; got {len(checked)}"
        )
    return checked


def validate_counter(counter: int) -> int:
    """Validate the ML-KEM-512 K-PKE.KeyGen PRF counter byte (0 through 3)."""
    return _require_int("counter", counter, COUNTER_MIN, COUNTER_MAX)


def validate_request_id(request_id: int) -> int:
    return _require_int("request_id", request_id, 0, (1 << 32) - 1)


def build_descriptor(counter: int, request_id: int) -> bytes:
    """Build the immutable 16-byte request descriptor after validation."""
    return struct.pack(
        "<BBBBBBBBI4s",
        ABI_VERSION,
        OPCODE_MLKEM512_NOISE_NTT,
        PARAMETER_MLKEM512,
        0,
        validate_counter(counter),
        ETA1,
        PRF_BYTES,
        0,
        validate_request_id(request_id),
        b"\x00" * 4,
    )


def validate_request(
    sigma: bytes | bytearray | memoryview, counter: int, request_id: int
) -> tuple[bytes, bytes]:
    return validate_sigma(sigma), build_descriptor(counter, request_id)


def result_sentinel() -> bytes:
    record = bytearray(RESULT_BYTES)
    record[RESULT_HEADER_BYTES:] = b"\xff" * (RESULT_BYTES - RESULT_HEADER_BYTES)
    return bytes(record)


def _result_bytes(result: bytes | bytearray | memoryview | Sequence[int]) -> bytes:
    try:
        raw = bytes(result)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "terminal result must be bytes-like or a uint8 sequence"
        ) from exc
    if len(raw) != RESULT_BYTES:
        raise Dr2bAbiError(
            f"terminal result must contain exactly {RESULT_BYTES} bytes; got {len(raw)}"
        )
    return raw


def parse_result(
    result: bytes | bytearray | memoryview | Sequence[int], request_id: int
) -> list[int]:
    """Return a complete canonical NTT polynomial, or fail closed."""
    expected_request_id = validate_request_id(request_id)
    raw = _result_bytes(result)
    magic, echoed_request_id, status = struct.unpack_from("<III", raw, 0)
    coefficient_count = struct.unpack_from("<H", raw, 12)[0]
    stages = raw[14]
    reserved = raw[15]
    coefficients = list(struct.unpack_from("<256h", raw, RESULT_HEADER_BYTES))
    if magic != RESULT_MAGIC:
        raise Dr2bAbiError("terminal result magic was not replaced by the device")
    if echoed_request_id != expected_request_id:
        raise Dr2bAbiError("terminal result request_id does not echo the request")
    if status not in VALID_STATUSES:
        raise Dr2bAbiError(f"terminal result has unknown status {status}")
    if stages != 7 or reserved != 0:
        raise Dr2bAbiError("terminal result stage count or reserved byte is invalid")
    if status == STATUS_OK:
        if coefficient_count != N:
            raise Dr2bAbiError("successful terminal result lacks all 256 NTT lanes")
        if any(value < 0 or value >= Q for value in coefficients):
            raise Dr2bAbiError(
                "successful terminal result contains non-canonical NTT lanes"
            )
        return coefficients
    if coefficient_count != 0 or any(coefficients):
        raise Dr2bAbiError("terminal error result must have a fixed zero payload")
    name = "BAD_DESCRIPTOR" if status == STATUS_BAD_DESCRIPTOR else "BAD_TOKEN"
    raise Dr2bOperationError(
        f"DR2b device graph returned {name}; no host fallback is available"
    )


__all__ = [
    "ABI_VERSION",
    "COUNTER_MAX",
    "COUNTER_MIN",
    "DESCRIPTOR_BYTES",
    "ETA1",
    "OPCODE_MLKEM512_NOISE_NTT",
    "PARAMETER_MLKEM512",
    "PRF_BYTES",
    "PRF_TOKEN_BYTES",
    "RESULT_BYTES",
    "RESULT_HEADER_BYTES",
    "RESULT_MAGIC",
    "SIGMA_BYTES",
    "STATUS_BAD_DESCRIPTOR",
    "STATUS_BAD_TOKEN",
    "STATUS_OK",
    "Dr2bAbiError",
    "Dr2bOperationError",
    "N",
    "Q",
    "build_descriptor",
    "parse_result",
    "result_sentinel",
    "validate_counter",
    "validate_request",
    "validate_request_id",
    "validate_sigma",
]
