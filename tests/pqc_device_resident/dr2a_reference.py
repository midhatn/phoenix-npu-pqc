"""Independent test-only oracle for bounded ML-KEM-512 SHAKE128/SampleNTT.

This module imports neither DR2a production Python nor any production ABI.  It
uses hashlib's SHAKE128 and a separate FIPS 203 three-byte parser so it can
detect a shared Keccak or candidate-decoding error.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

N = 256
Q = 3329
RATE = 168
BLOCK_CAP = 5


@dataclass(frozen=True)
class ReferenceResult:
    """The complete-or-empty contract used by the independent test oracle."""

    coefficients: tuple[int, ...]
    accepted_count: int
    blocks_executed: int
    limit_exceeded: bool


def _validate_inputs(rho: bytes, j: int, i: int, max_blocks: int) -> None:
    if type(rho) is not bytes or len(rho) != 32:
        raise ValueError("reference rho must be exactly 32 immutable bytes")
    if type(j) is not int or type(i) is not int or not (0 <= j < 2 and 0 <= i < 2):
        raise ValueError("reference coordinates must be Python ints in [0, 1]")
    if type(max_blocks) is not int or max_blocks < 0:
        raise ValueError("reference max_blocks must be a nonnegative Python int")


def shake128_stream_reference(
    rho: bytes, j: int, i: int, max_blocks: int = BLOCK_CAP
) -> bytes:
    """Return the independent SHAKE128 stream for FIPS 203 ``rho || j || i``."""
    _validate_inputs(rho, j, i, max_blocks)
    return hashlib.shake_128(rho + bytes((j, i))).digest(max_blocks * RATE)


def accepted_candidates_from_stream(stream: bytes) -> tuple[int, ...]:
    """Parse complete three-byte FIPS 203 candidate pairs independently."""
    if len(stream) % 3:
        raise ValueError("reference stream must end on a complete three-byte candidate")
    accepted: list[int] = []
    for offset in range(0, len(stream), 3):
        b0, b1, b2 = stream[offset : offset + 3]
        d1 = b0 + 256 * (b1 & 0x0F)
        d2 = (b1 >> 4) + 16 * b2
        if d1 < Q:
            accepted.append(d1)
        if d2 < Q:
            accepted.append(d2)
    return tuple(accepted)


def samplentt_reference(
    rho: bytes, j: int, i: int, max_blocks: int = BLOCK_CAP
) -> ReferenceResult:
    """Independently derive one bounded ML-KEM SampleNTT polynomial."""
    stream = shake128_stream_reference(rho, j, i, max_blocks)
    accepted = accepted_candidates_from_stream(stream)
    if len(accepted) < N:
        return ReferenceResult((), 0, max_blocks, True)
    return ReferenceResult(accepted[:N], N, max_blocks, False)
