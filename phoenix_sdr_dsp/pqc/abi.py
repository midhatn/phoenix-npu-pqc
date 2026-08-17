"""Stable host ABI for the DR0 M33 device-resident product graph.

The graph accepts two *plain* ML-DSA ring polynomials and returns one plain,
canonical polynomial.  The Montgomery factors used by M33a NTT/base-multiply/
INTT are contained in the AIE kernel; callers must not repair or rescale the
terminal result on the host.
"""

from __future__ import annotations

from collections.abc import Sequence

N = 256
Q = 8_380_417

# Inputs use M33a's documented signed, centered-safe operand envelope.  The
# value zero is included and either standard [0, q) or centered coefficients
# are accepted.  The terminal output is canonical [0, q).
COEFFICIENT_MIN = -(Q - 1)
COEFFICIENT_MAX = Q - 1
OUTPUT_MIN = 0
OUTPUT_MAX = Q - 1

ELEMENT_BYTES = 4
POLYNOMIAL_BYTES = N * ELEMENT_BYTES
INGRESS_COUNT = 2
EGRESS_COUNT = 1


def validate_polynomial(name: str, values: Sequence[int]) -> tuple[int, ...]:
    """Validate a host polynomial before IRON/XRT is imported or invoked.

    DR0 deliberately accepts only ordinary Python integer sequences.  This
    avoids implicit float truncation, bool-as-int ambiguity, object-array
    conversions, and host-dependent integer narrowing at the device boundary.
    """
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{name} must be a sequence of exactly {N} Python ints")
    if len(values) != N:
        raise ValueError(f"{name} must contain exactly {N} coefficients; got {len(values)}")

    checked: list[int] = []
    for index, value in enumerate(values):
        if type(value) is not int:  # strict: intentionally rejects bool and numpy scalar types
            raise TypeError(f"{name}[{index}] must be a Python int; got {type(value).__name__}")
        if not COEFFICIENT_MIN <= value <= COEFFICIENT_MAX:
            raise ValueError(
                f"{name}[{index}]={value} is outside the DR0 input range "
                f"[{COEFFICIENT_MIN}, {COEFFICIENT_MAX}]"
            )
        checked.append(value)
    return tuple(checked)


def reference_negacyclic_product(
    a: Sequence[int], b: Sequence[int]
) -> list[int]:
    """Independent O(n²) reference for ``Z_q[x] / (x^256 + 1)``.

    This reference intentionally uses direct convolution rather than an NTT or
    any M33a Montgomery helper.  It is the off-device oracle for DR0's terminal
    ABI and returns a canonical coefficient vector in ``[0, q)``.
    """
    left = validate_polynomial("a", a)
    right = validate_polynomial("b", b)
    accum = [0] * N
    for i, left_i in enumerate(left):
        for j, right_j in enumerate(right):
            target = i + j
            if target < N:
                accum[target] += left_i * right_j
            else:
                accum[target - N] -= left_i * right_j
    return [coefficient % Q for coefficient in accum]
