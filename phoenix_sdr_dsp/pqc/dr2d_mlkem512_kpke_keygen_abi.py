"""Fixed fail-closed ABI for the complete resident ML-KEM-512 K-PKE.KeyGen.

DR2d accepts only raw FIPS 203 entropy ``d`` and an immutable request
descriptor.  The device derives ``rho || sigma = G(d || k)`` and returns one
terminal record containing the byte-exact K-PKE public and private keys.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Sequence

N = 256
Q = 3329
K = 2
D_BYTES = 32
DESCRIPTOR_BYTES = 16
G_INPUT_BYTES = D_BYTES + 1
G_OUTPUT_BYTES = 64
RHO_BYTES = 32
SIGMA_BYTES = 32
POLY_ENCODED_BYTES = 384
EK_PKE_BYTES = RHO_BYTES + K * POLY_ENCODED_BYTES
DK_PKE_BYTES = K * POLY_ENCODED_BYTES
SECRET_TOKEN_BYTES = 2096
ROW_STATE_TOKEN_BYTES = 2096
ROW_MATRIX_TOKEN_BYTES = 3120
PRIVATE_TOKEN_HEADER_BYTES = 32
PRIVATE_TOKEN_BYTES = PRIVATE_TOKEN_HEADER_BYTES + RHO_BYTES + 4 * N * 2
RESULT_HEADER_BYTES = 20
RESULT_BYTES = RESULT_HEADER_BYTES + EK_PKE_BYTES + DK_PKE_BYTES

ABI_VERSION = 1
OPCODE_MLKEM512_KPKE_KEYGEN = 0x24
PARAMETER_MLKEM512 = 0x52
ETA1 = 3
SAMPLE_NTT_BLOCK_CAP = 5
RESULT_MAGIC = 0x4432524D  # Little-endian bytes: b"MR2D".
STATUS_OK = 0
STATUS_LIMIT_EXCEEDED = 1
STATUS_BAD_DESCRIPTOR = 2
STATUS_BAD_TOKEN = 3
VALID_STATUSES = frozenset(
    (STATUS_OK, STATUS_LIMIT_EXCEEDED, STATUS_BAD_DESCRIPTOR, STATUS_BAD_TOKEN)
)


class Dr2dAbiError(ValueError):
    """A public DR2d request or terminal record violates the fixed ABI."""


class Dr2dOperationError(RuntimeError):
    """The resident graph returned a valid fixed-zero-payload terminal error."""


def _require_int(name: str, value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int; got {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise Dr2dAbiError(f"{name}={value} is outside [{minimum}, {maximum}]")
    return value


def validate_d(d: bytes | bytearray | memoryview) -> bytes:
    """Return immutable, exact-length raw KeyGen entropy before runtime loading."""
    if not isinstance(d, (bytes, bytearray, memoryview)):
        raise TypeError("d must be bytes-like and exactly 32 bytes")
    checked = bytes(d)
    if len(checked) != D_BYTES:
        raise Dr2dAbiError(
            f"d must contain exactly {D_BYTES} bytes; got {len(checked)}"
        )
    return checked


def validate_request_id(request_id: int) -> int:
    return _require_int("request_id", request_id, 0, (1 << 32) - 1)


def build_descriptor(request_id: int) -> bytes:
    """Build the v1 descriptor; it carries no key material or host crypto output."""
    return struct.pack(
        "<BBBBBBBBI4s",
        ABI_VERSION,
        OPCODE_MLKEM512_KPKE_KEYGEN,
        PARAMETER_MLKEM512,
        0,
        K,
        ETA1,
        SAMPLE_NTT_BLOCK_CAP,
        0,
        validate_request_id(request_id),
        b"\x00" * 4,
    )


def validate_request(
    d: bytes | bytearray | memoryview, request_id: int
) -> tuple[bytes, bytes]:
    """Validate the two host ingress records without loading native code."""
    return validate_d(d), build_descriptor(request_id)


def result_sentinel() -> bytes:
    """Create a visibly unwritten terminal record, never a valid key."""
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
        raise Dr2dAbiError(
            f"terminal result must contain exactly {RESULT_BYTES} bytes; got {len(raw)}"
        )
    return raw


def _validate_poly12(payload: bytes, offset: int, name: str) -> None:
    for index in range(N // 2):
        base = offset + 3 * index
        first = payload[base] | ((payload[base + 1] & 0x0F) << 8)
        second = (payload[base + 1] >> 4) | (payload[base + 2] << 4)
        if first >= Q or second >= Q:
            raise Dr2dAbiError(
                f"successful terminal result has non-canonical {name} lanes"
            )


def parse_result(
    result: bytes | bytearray | memoryview | Sequence[int], request_id: int
) -> tuple[bytes, bytes]:
    """Return byte-exact ``(ekPKE, dkPKE)`` or fail closed without any fallback."""
    expected_request_id = validate_request_id(request_id)
    raw = _result_bytes(result)
    magic, echoed_request_id, status, ek_bytes, dk_bytes, checksum = struct.unpack_from(
        "<IIIHHI", raw, 0
    )
    payload = raw[RESULT_HEADER_BYTES:]
    if magic != RESULT_MAGIC:
        raise Dr2dAbiError("terminal result magic was not replaced by the device")
    if echoed_request_id != expected_request_id:
        raise Dr2dAbiError("terminal result request_id does not echo the request")
    if status not in VALID_STATUSES:
        raise Dr2dAbiError(f"terminal result has unknown status {status}")
    if status == STATUS_OK:
        if (ek_bytes, dk_bytes) != (EK_PKE_BYTES, DK_PKE_BYTES):
            raise Dr2dAbiError("successful terminal result has invalid key lengths")
        if checksum != (zlib.crc32(payload) & 0xFFFFFFFF):
            raise Dr2dAbiError(
                "successful terminal result checksum does not match payload"
            )
        if not any(payload):
            raise Dr2dAbiError(
                "successful terminal result has forbidden all-zero payload"
            )
        _validate_poly12(payload, 0, "t_hat[0]")
        _validate_poly12(payload, POLY_ENCODED_BYTES, "t_hat[1]")
        _validate_poly12(payload, EK_PKE_BYTES, "s_hat[0]")
        _validate_poly12(payload, EK_PKE_BYTES + POLY_ENCODED_BYTES, "s_hat[1]")
        return payload[:EK_PKE_BYTES], payload[EK_PKE_BYTES:]
    if ek_bytes != 0 or dk_bytes != 0 or checksum != 0 or any(payload):
        raise Dr2dAbiError("terminal error result must have fixed zero key payloads")
    names = {
        STATUS_LIMIT_EXCEEDED: "LIMIT_EXCEEDED",
        STATUS_BAD_DESCRIPTOR: "BAD_DESCRIPTOR",
        STATUS_BAD_TOKEN: "BAD_TOKEN",
    }
    raise Dr2dOperationError(
        f"DR2d device graph returned {names[status]}; no host fallback is available"
    )


__all__ = [
    "ABI_VERSION",
    "DESCRIPTOR_BYTES",
    "DK_PKE_BYTES",
    "D_BYTES",
    "EK_PKE_BYTES",
    "ETA1",
    "G_INPUT_BYTES",
    "G_OUTPUT_BYTES",
    "OPCODE_MLKEM512_KPKE_KEYGEN",
    "PARAMETER_MLKEM512",
    "PRIVATE_TOKEN_BYTES",
    "RESULT_BYTES",
    "RESULT_HEADER_BYTES",
    "RESULT_MAGIC",
    "ROW_MATRIX_TOKEN_BYTES",
    "ROW_STATE_TOKEN_BYTES",
    "SAMPLE_NTT_BLOCK_CAP",
    "SECRET_TOKEN_BYTES",
    "STATUS_BAD_DESCRIPTOR",
    "STATUS_BAD_TOKEN",
    "STATUS_LIMIT_EXCEEDED",
    "STATUS_OK",
    "Dr2dAbiError",
    "Dr2dOperationError",
    "K",
    "N",
    "Q",
    "build_descriptor",
    "parse_result",
    "result_sentinel",
    "validate_d",
    "validate_request",
    "validate_request_id",
]
