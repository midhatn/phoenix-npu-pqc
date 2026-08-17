"""Independent direct FIPS 203 oracle for one ML-KEM-512 KeyGen row.

This module imports no DR2c production code.  SHAKE, SampleNTT, CBD3, NTT, and
MultiplyNTTs are each expressed directly for off-hardware validation.
"""

from __future__ import annotations

import hashlib

N, Q, RATE128, ETA1, BLOCK_CAP = 256, 3329, 168, 3, 5


def _validate(rho: bytes, sigma: bytes, row_index: int) -> None:
    if type(rho) is not bytes or len(rho) != 32:
        raise ValueError("reference rho must be exactly 32 immutable bytes")
    if type(sigma) is not bytes or len(sigma) != 32:
        raise ValueError("reference sigma must be exactly 32 immutable bytes")
    if type(row_index) is not int or not 0 <= row_index <= 1:
        raise ValueError("reference row index must be a Python int in 0..1")


def _brv7(value: int) -> int:
    return int(f"{value:07b}"[::-1], 2)


def _zetas() -> tuple[int, ...]:
    return tuple(pow(17, _brv7(index), Q) for index in range(128))


ZETAS = _zetas()


def sample_ntt_reference(rho: bytes, column: int, row_index: int) -> tuple[int, ...]:
    if type(rho) is not bytes or len(rho) != 32 or type(column) is not int or column not in (0, 1) or type(row_index) is not int or row_index not in (0, 1):
        raise ValueError("SampleNTT reference requires rho[32] and matrix coordinates in 0..1")
    stream = hashlib.shake_128(rho + bytes((column, row_index))).digest(BLOCK_CAP * RATE128)
    output: list[int] = []
    for offset in range(0, len(stream), 3):
        b0, b1, b2 = stream[offset : offset + 3]
        for candidate in (b0 + 256 * (b1 & 0x0F), (b1 >> 4) + 16 * b2):
            if candidate < Q:
                output.append(candidate)
                if len(output) == N:
                    return tuple(output)
    raise ValueError("bounded SampleNTT reference exhausted 280 candidate iterations")


def _cbd3(sigma: bytes, counter: int) -> tuple[int, ...]:
    raw = hashlib.shake_256(sigma + bytes((counter,))).digest(192)
    return tuple(
        sum((raw[(6 * i + bit) >> 3] >> ((6 * i + bit) & 7)) & 1 for bit in range(3))
        - sum((raw[(6 * i + bit) >> 3] >> ((6 * i + bit) & 7)) & 1 for bit in range(3, 6))
        for i in range(N)
    )


def ntt_reference(coefficients: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if len(coefficients) != N:
        raise ValueError("NTT reference requires 256 coefficients")
    result = [value % Q for value in coefficients]
    index, length = 1, 128
    while length >= 2:
        for start in range(0, N, 2 * length):
            zeta = ZETAS[index]
            index += 1
            for lane in range(start, start + length):
                term = zeta * result[lane + length] % Q
                result[lane + length] = (result[lane] - term) % Q
                result[lane] = (result[lane] + term) % Q
        length //= 2
    return tuple(result)


def noise_ntt_reference(sigma: bytes, counter: int) -> tuple[int, ...]:
    if type(sigma) is not bytes or len(sigma) != 32 or type(counter) is not int or not 0 <= counter <= 3:
        raise ValueError("noise reference requires sigma[32] and a counter in 0..3")
    return ntt_reference(_cbd3(sigma, counter))


def multiply_ntts_reference(a_hat: tuple[int, ...], b_hat: tuple[int, ...]) -> tuple[int, ...]:
    if len(a_hat) != N or len(b_hat) != N:
        raise ValueError("MultiplyNTTs reference requires two 256-lane polynomials")
    result = [0] * N
    for index in range(64):
        gamma = ZETAS[64 + index]
        for offset, zeta in ((0, gamma), (2, Q - gamma)):
            lane = 4 * index + offset
            result[lane] = (a_hat[lane] * b_hat[lane] + zeta * a_hat[lane + 1] * b_hat[lane + 1]) % Q
            result[lane + 1] = (a_hat[lane] * b_hat[lane + 1] + a_hat[lane + 1] * b_hat[lane]) % Q
    return tuple(result)


def keygen_row_reference(rho: bytes, sigma: bytes, row_index: int) -> tuple[int, ...]:
    """Compute t-hat[row] = A-hat[row,0] o s-hat[0] + A-hat[row,1] o s-hat[1] + e-hat[row]."""
    _validate(rho, sigma, row_index)
    a0 = sample_ntt_reference(rho, 0, row_index)
    a1 = sample_ntt_reference(rho, 1, row_index)
    s0, s1 = noise_ntt_reference(sigma, 0), noise_ntt_reference(sigma, 1)
    error = noise_ntt_reference(sigma, row_index + 2)
    product0, product1 = multiply_ntts_reference(a0, s0), multiply_ntts_reference(a1, s1)
    return tuple((product0[i] + product1[i] + error[i]) % Q for i in range(N))
