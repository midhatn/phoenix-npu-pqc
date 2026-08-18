"""Independent direct FIPS 203 ML-KEM-512 K-PKE.KeyGen oracle for DR2d tests.

This test-only module imports no DR2d production code or previous DR2
references.  It directly implements G, SampleNTT, CBD3, NTT, MultiplyNTTs,
and the FIPS 203 12-bit ByteEncode layout.
"""

from __future__ import annotations

import hashlib

N, Q, K, RATE128, ETA1, BLOCK_CAP = 256, 3329, 2, 168, 3, 5


def _brv7(value: int) -> int:
    return int(f"{value:07b}"[::-1], 2)


ZETAS = tuple(pow(17, _brv7(index), Q) for index in range(128))


def _validate_d(d: bytes) -> None:
    if type(d) is not bytes or len(d) != 32:
        raise ValueError("reference d must be exactly 32 immutable bytes")


def _sample_ntt(rho: bytes, column: int, row: int) -> tuple[int, ...]:
    stream = hashlib.shake_128(rho + bytes((column, row))).digest(BLOCK_CAP * RATE128)
    accepted: list[int] = []
    for offset in range(0, len(stream), 3):
        b0, b1, b2 = stream[offset : offset + 3]
        for candidate in (b0 + 256 * (b1 & 0x0F), (b1 >> 4) + 16 * b2):
            if candidate < Q:
                accepted.append(candidate)
                if len(accepted) == N:
                    return tuple(accepted)
    raise ValueError("bounded FIPS 203 SampleNTT reference exhausted its five blocks")


def _ntt(coefficients: tuple[int, ...]) -> tuple[int, ...]:
    values, index, length = list(coefficients), 1, 128
    while length >= 2:
        for start in range(0, N, 2 * length):
            twiddle = ZETAS[index]
            index += 1
            for lane in range(start, start + length):
                term = twiddle * values[lane + length] % Q
                values[lane + length] = (values[lane] - term) % Q
                values[lane] = (values[lane] + term) % Q
        length //= 2
    return tuple(values)


def _noise_ntt(sigma: bytes, counter: int) -> tuple[int, ...]:
    raw = hashlib.shake_256(sigma + bytes((counter,))).digest(192)
    coefficients = tuple(
        sum((raw[(6 * i + bit) >> 3] >> ((6 * i + bit) & 7)) & 1 for bit in range(3))
        - sum(
            (raw[(6 * i + bit) >> 3] >> ((6 * i + bit) & 7)) & 1 for bit in range(3, 6)
        )
        for i in range(N)
    )
    return _ntt(tuple(value % Q for value in coefficients))


def _multiply_ntts(a_hat: tuple[int, ...], b_hat: tuple[int, ...]) -> tuple[int, ...]:
    out = [0] * N
    for index in range(64):
        gamma, lane = ZETAS[64 + index], 4 * index
        out[lane] = (
            a_hat[lane] * b_hat[lane] + gamma * a_hat[lane + 1] * b_hat[lane + 1]
        ) % Q
        out[lane + 1] = (
            a_hat[lane] * b_hat[lane + 1] + a_hat[lane + 1] * b_hat[lane]
        ) % Q
        out[lane + 2] = (
            a_hat[lane + 2] * b_hat[lane + 2]
            - gamma * a_hat[lane + 3] * b_hat[lane + 3]
        ) % Q
        out[lane + 3] = (
            a_hat[lane + 2] * b_hat[lane + 3] + a_hat[lane + 3] * b_hat[lane + 2]
        ) % Q
    return tuple(out)


def _encode12(polynomial: tuple[int, ...]) -> bytes:
    if len(polynomial) != N or any(not 0 <= lane < Q for lane in polynomial):
        raise ValueError("ByteEncode12 requires one canonical 256-lane polynomial")
    output = bytearray(384)
    for index in range(128):
        a, b = polynomial[2 * index], polynomial[2 * index + 1]
        output[3 * index] = a & 0xFF
        output[3 * index + 1] = (a >> 8) | ((b & 0x0F) << 4)
        output[3 * index + 2] = b >> 4
    return bytes(output)


def kpke_keygen_reference(d: bytes) -> tuple[bytes, bytes]:
    """Return the exact FIPS 203 ML-KEM-512 ``(ekPKE, dkPKE)`` for raw ``d``."""
    _validate_d(d)
    rho_sigma = hashlib.sha3_512(d + bytes((K,))).digest()
    rho, sigma = rho_sigma[:32], rho_sigma[32:]
    s0, s1 = _noise_ntt(sigma, 0), _noise_ntt(sigma, 1)
    t: list[tuple[int, ...]] = []
    for row in range(K):
        a0, a1 = _sample_ntt(rho, 0, row), _sample_ntt(rho, 1, row)
        error = _noise_ntt(sigma, row + K)
        p0, p1 = _multiply_ntts(a0, s0), _multiply_ntts(a1, s1)
        t.append(tuple((p0[i] + p1[i] + error[i]) % Q for i in range(N)))
    return _encode12(t[0]) + _encode12(t[1]) + rho, _encode12(s0) + _encode12(s1)


# Test-only accessors so directed per-store-path regressions can compare a
# single repaired production store region against this independent oracle.
sample_ntt_reference = _sample_ntt
noise_ntt_reference_dr2d = _noise_ntt
multiply_ntts_reference = _multiply_ntts
