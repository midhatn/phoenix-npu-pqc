"""Independent test-only oracle for fixed ML-DSA-44 ExpandA/RejNTT.

This module deliberately imports neither the DR1 graph nor its ABI module.  It
uses Python's hashlib SHAKE128 implementation and separately implements the
three-byte candidate rule so an exact-output comparison can detect a shared
Keccak/parser bug in production sources.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

N = 256
Q = 8_380_417
RATE = 168


@dataclass(frozen=True)
class ReferenceResult:
    coefficients: tuple[int, ...]
    accepted_count: int
    blocks_executed: int
    limit_exceeded: bool


def _validate_inputs(rho: bytes, j: int, i: int, max_blocks: int) -> None:
    if type(rho) is not bytes or len(rho) != 32:
        raise ValueError("reference rho must be exactly 32 immutable bytes")
    if type(j) is not int or type(i) is not int or not (0 <= j < 4 and 0 <= i < 4):
        raise ValueError("reference coordinates must be Python ints in [0, 3]")
    if type(max_blocks) is not int or max_blocks < 0:
        raise ValueError("reference max_blocks must be a nonnegative Python int")


def shake128_stream_reference(rho: bytes, j: int, i: int, max_blocks: int = 8) -> bytes:
    """Return the independent fixed-rate SHAKE stream for one DR1 request."""
    _validate_inputs(rho, j, i, max_blocks)
    return hashlib.shake_128(rho + bytes((j, i))).digest(max_blocks * RATE)


def accepted_candidates_from_stream(stream: bytes) -> tuple[int, ...]:
    """Parse every complete three-byte candidate without a production import."""
    if len(stream) % 3:
        raise ValueError("reference stream must end on a complete three-byte candidate")
    accepted: list[int] = []
    for offset in range(0, len(stream), 3):
        candidate = (
            stream[offset]
            | (stream[offset + 1] << 8)
            | (stream[offset + 2] << 16)
        ) & 0x7FFFFF
        if candidate < Q:
            accepted.append(candidate)
    return tuple(accepted)


def expanda_rejntt_reference(rho: bytes, j: int, i: int, max_blocks: int = 8) -> ReferenceResult:
    """Independently derive one bounded ``SHAKE128(rho || j || i)`` polynomial."""
    stream = shake128_stream_reference(rho, j, i, max_blocks)
    accepted = accepted_candidates_from_stream(stream)
    if len(accepted) != N and len(accepted) < N:
        return ReferenceResult((), 0, max_blocks, True)
    return ReferenceResult(accepted[:N], N, max_blocks, False)
