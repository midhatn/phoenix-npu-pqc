"""Independent FIPS 203 reference for DR2b, with no production imports."""

from __future__ import annotations

import hashlib

N, Q, ETA1, PRF_BYTES = 256, 3329, 3, 192


def prf_eta1_reference(sigma: bytes, counter: int) -> bytes:
    if (
        type(sigma) is not bytes
        or len(sigma) != 32
        or type(counter) is not int
        or not 0 <= counter <= 3
    ):
        raise ValueError("reference requires sigma[32] and a counter in 0..3")
    return hashlib.shake_256(sigma + bytes((counter,))).digest(PRF_BYTES)


def cbd3_reference(prf: bytes) -> tuple[int, ...]:
    if type(prf) is not bytes or len(prf) != PRF_BYTES:
        raise ValueError("CBD3 reference requires exactly 192 PRF bytes")
    return tuple(
        sum((prf[(6 * i + bit) >> 3] >> ((6 * i + bit) & 7)) & 1 for bit in range(3))
        - sum(
            (prf[(6 * i + bit) >> 3] >> ((6 * i + bit) & 7)) & 1 for bit in range(3, 6)
        )
        for i in range(N)
    )


def _bit_reverse7(value: int) -> int:
    return int(f"{value:07b}"[::-1], 2)


def ntt_reference(coefficients: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if len(coefficients) != N:
        raise ValueError("NTT reference requires 256 coefficients")
    r = [value % Q for value in coefficients]
    k, length = 1, 128
    while length >= 2:
        for start in range(0, N, 2 * length):
            zeta = pow(17, _bit_reverse7(k), Q)
            k += 1
            for index in range(start, start + length):
                t = zeta * r[index + length] % Q
                r[index + length] = (r[index] - t) % Q
                r[index] = (r[index] + t) % Q
        length //= 2
    return tuple(r)


def noise_ntt_reference(sigma: bytes, counter: int) -> tuple[int, ...]:
    return ntt_reference(cbd3_reference(prf_eta1_reference(sigma, counter)))
