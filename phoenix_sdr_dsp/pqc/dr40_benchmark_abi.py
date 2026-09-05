# SPDX-License-Identifier: Apache-2.0
"""Milestone DR40: Reproducible High-Throughput Hardware Benchmark Protocol & Profiling Battery.
Execution Boundary: [HOST RUNTIME] / [HOST FORMATTER].
Enforces mathematical oracle equivalence, fail-closed validation, and microsecond-level profiling.
"""

from dataclasses import dataclass
import math
import struct
import time
from typing import Dict, List, Optional, Tuple

MAGIC_HEADER = 0x44523430  # 'DR40'

# Status Codes
STATUS_SUCCESS = 0x00000000
STATUS_ERR_INVALID_MAGIC = 0x80000001
STATUS_ERR_UNSUPPORTED_MODE = 0x80000002
STATUS_ERR_INVALID_BATCH = 0x80000003

# Benchmark Workload Operation Modes
MODE_BENCH_NTT_BUTTERFLY = 0x00000001
MODE_BENCH_KECCAK_F1600 = 0x00000002
MODE_BENCH_VECTOR_MAC = 0x00000003
MODE_BENCH_SAMPLE_NTT = 0x00000004

DESCRIPTOR_SIZE = 64
REQUEST_BUFFER_SIZE = 4096
RESULT_BUFFER_SIZE = 2048

# Cryptographic Modulus for ML-KEM
MODULUS_Q = 3329
MONTGOMERY_R = 3328  # 2^16 mod 3329 = 3328
MONTGOMERY_QINV = 62209  # -q^{-1} mod 2^16 = 62209


@dataclass
class BenchmarkDescriptor:
    op_mode: int
    batch_size: int
    warmup_iters: int = 2
    flags: int = 0
    param_0: int = 0
    param_1: int = 0
    seq_id: int = 1
    magic: int = MAGIC_HEADER

    def pack(self) -> bytes:
        data = bytearray(DESCRIPTOR_SIZE)
        struct.pack_into(
            "<IIIIIIII",
            data,
            0,
            self.magic,
            self.op_mode,
            self.batch_size,
            self.warmup_iters,
            self.flags,
            self.param_0,
            self.param_1,
            0,  # reserved
        )
        struct.pack_into("<I", data, 32, self.seq_id)
        return bytes(data)

    @classmethod
    def unpack(cls, buf: bytes) -> 'BenchmarkDescriptor':
        if len(buf) < DESCRIPTOR_SIZE:
            raise ValueError(f"Buffer length {len(buf)} smaller than required {DESCRIPTOR_SIZE}")
        fields = struct.unpack_from("<IIIIIIII", buf, 0)
        seq_id = struct.unpack_from("<I", buf, 32)[0]
        return cls(
            magic=fields[0],
            op_mode=fields[1],
            batch_size=fields[2],
            warmup_iters=fields[3],
            flags=fields[4],
            param_0=fields[5],
            param_1=fields[6],
            seq_id=seq_id,
        )


@dataclass
class BenchmarkResultHeader:
    status: int
    op_mode: int
    batch_size: int
    iterations_completed: int
    checksum: int
    payload: bytes

    def pack(self) -> bytes:
        hdr = struct.pack(
            "<IIIII12x",
            self.status,
            self.op_mode,
            self.batch_size,
            self.iterations_completed,
            self.checksum,
        )
        payload_bytes = self.payload[:RESULT_BUFFER_SIZE - 32]
        pad_len = RESULT_BUFFER_SIZE - 32 - len(payload_bytes)
        return hdr + payload_bytes + (bytes(pad_len) if pad_len > 0 else b"")

    @classmethod
    def unpack(cls, buf: bytes) -> 'BenchmarkResultHeader':
        if len(buf) < 32:
            raise ValueError(f"Buffer length {len(buf)} smaller than header size 32")
        status, op_mode, batch_size, iters, checksum = struct.unpack_from("<IIIII", buf, 0)
        payload = buf[32:]
        return cls(
            status=status,
            op_mode=op_mode,
            batch_size=batch_size,
            iterations_completed=iters,
            checksum=checksum,
            payload=payload,
        )


@dataclass
class BenchmarkMetrics:
    op_mode: int
    batch_size: int
    total_wall_time_us: float
    latency_per_op_us: float
    ops_per_second: float
    throughput_mbs: float
    mean_us: float
    median_us: float
    min_us: float
    max_us: float
    stddev_us: float
    cv_percent: float


def montgomery_reduce(a: int) -> int:
    """Montgomery reduction for q = 3329: computes a * R^{-1} mod q."""
    t = (a * MONTGOMERY_QINV) & 0xFFFF
    res = (a - t * MODULUS_Q) >> 16
    if res < 0:
        res += MODULUS_Q
    return res % MODULUS_Q


def ntt_butterfly_layer_ref(poly: List[int], twiddle: int) -> List[int]:
    """Executes 128 radix-2 Cooley-Tukey butterflies across 256 coefficients."""
    res = list(poly)
    for i in range(128):
        u = res[i]
        v = res[i + 128]
        v_tw = (v * twiddle) % MODULUS_Q
        res[i] = (u + v_tw) % MODULUS_Q
        res[i + 128] = (u - v_tw + MODULUS_Q) % MODULUS_Q
    return res


def vector_mac_ref(poly_a: List[int], poly_b: List[int]) -> List[int]:
    """Pointwise polynomial multiplication: c[i] = (a[i] * b[i]) mod q."""
    return [(a * b) % MODULUS_Q for a, b in zip(poly_a, poly_b)]


def keccak_round_ref(state: List[int], round_idx: int) -> List[int]:
    """Single round of Keccak-f[1600] on 25 64-bit lanes."""
    rc_table = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
    ]
    rot = [
        0,  1, 62, 28, 27,
        36, 44,  6, 55, 20,
         3, 10, 43, 25, 39,
        41, 45, 15, 21,  8,
        18,  2, 61, 56, 14,
    ]
    # Theta
    c = [0] * 5
    for x in range(5):
        c[x] = state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20]
    d = [0] * 5
    for x in range(5):
        rol_c1 = ((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & 0xFFFFFFFFFFFFFFFF
        d[x] = c[(x + 4) % 5] ^ rol_c1

    theta_state = [state[i] ^ d[i % 5] for i in range(25)]

    # Rho and Pi
    b = [0] * 25
    for x in range(5):
        for y in range(5):
            idx = x + 5 * y
            r = rot[idx]
            val = theta_state[idx]
            rol_val = ((val << r) | (val >> (64 - r))) & 0xFFFFFFFFFFFFFFFF if r > 0 else val
            new_idx = y + 5 * ((2 * x + 3 * y) % 5)
            b[new_idx] = rol_val

    # Chi
    out_state = [0] * 25
    for x in range(5):
        for y in range(5):
            idx = x + 5 * y
            out_state[idx] = b[idx] ^ ((~b[((x + 1) % 5) + 5 * y]) & b[((x + 2) % 5) + 5 * y]) & 0xFFFFFFFFFFFFFFFF

    # Iota
    out_state[0] ^= rc_table[round_idx % len(rc_table)]
    return out_state


def sample_ntt_ref(seed_bytes: bytes) -> Tuple[List[int], int]:
    """Rejection sampling: extracts coefficients in [0, 3329) from 12-bit chunks."""
    coeffs = []
    i = 0
    while len(coeffs) < 256 and i + 2 < len(seed_bytes):
        b0 = seed_bytes[i]
        b1 = seed_bytes[i + 1]
        b2 = seed_bytes[i + 2]
        d1 = b0 | ((b1 & 0x0F) << 8)
        d2 = (b1 >> 4) | (b2 << 4)
        if d1 < MODULUS_Q and len(coeffs) < 256:
            coeffs.append(d1)
        if d2 < MODULUS_Q and len(coeffs) < 256:
            coeffs.append(d2)
        i += 3
    while len(coeffs) < 256:
        coeffs.append(0)
    return coeffs, i


def compute_reference_oracle(
    op_mode: int,
    request_bytes: bytes,
    batch_size: int,
    warmup_iters: int = 0,
    param_0: int = 0,
) -> BenchmarkResultHeader:
    """Independent Host Reference Oracle for DR40 Benchmark Workloads."""
    if batch_size <= 0:
        return BenchmarkResultHeader(
            status=STATUS_ERR_INVALID_BATCH,
            op_mode=op_mode,
            batch_size=batch_size,
            iterations_completed=0,
            checksum=0,
            payload=bytes(RESULT_BUFFER_SIZE - 32),
        )

    payload = bytearray(RESULT_BUFFER_SIZE - 32)
    total_iters = warmup_iters + batch_size
    checksum = 0

    if op_mode == MODE_BENCH_NTT_BUTTERFLY:
        poly = [struct.unpack_from("<H", request_bytes, i * 2)[0] % MODULUS_Q for i in range(256)]
        twiddle = 1753  # Standard ML-KEM twiddle
        for it in range(total_iters):
            poly = ntt_butterfly_layer_ref(poly, twiddle)
            twiddle = (twiddle * 17) % MODULUS_Q
            if twiddle == 0:
                twiddle = 1

        for i, val in enumerate(poly):
            struct.pack_into("<H", payload, i * 2, val)
            checksum = (checksum + val) & 0xFFFFFFFF

    elif op_mode == MODE_BENCH_KECCAK_F1600:
        rounds = param_0 if param_0 > 0 else 24
        state = [struct.unpack_from("<Q", request_bytes, i * 8)[0] for i in range(25)]
        for it in range(total_iters):
            for r in range(rounds):
                state = keccak_round_ref(state, r)

        for i, val in enumerate(state):
            struct.pack_into("<Q", payload, i * 8, val)
            checksum = (checksum + (val & 0xFFFFFFFF) + (val >> 32)) & 0xFFFFFFFF

    elif op_mode == MODE_BENCH_VECTOR_MAC:
        poly_a = [struct.unpack_from("<H", request_bytes, i * 2)[0] % MODULUS_Q for i in range(256)]
        poly_b = [struct.unpack_from("<H", request_bytes, 512 + i * 2)[0] % MODULUS_Q for i in range(256)]
        accum = [0] * 256
        for it in range(total_iters):
            prod = vector_mac_ref(poly_a, poly_b)
            accum = [(acc + p) % MODULUS_Q for acc, p in zip(accum, prod)]
            poly_b = [(b + 3) % MODULUS_Q for b in poly_b]

        for i, val in enumerate(accum):
            struct.pack_into("<H", payload, i * 2, val)
            checksum = (checksum + val) & 0xFFFFFFFF

    elif op_mode == MODE_BENCH_SAMPLE_NTT:
        seed = request_bytes[:768]
        coeffs, _ = sample_ntt_ref(seed)
        cur = list(coeffs)
        for it in range(total_iters):
            cur = [(c * 3 + 7) % MODULUS_Q for c in cur]

        for i, val in enumerate(cur):
            struct.pack_into("<H", payload, i * 2, val)
            checksum = (checksum + val) & 0xFFFFFFFF

    else:
        return BenchmarkResultHeader(
            status=STATUS_ERR_UNSUPPORTED_MODE,
            op_mode=op_mode,
            batch_size=batch_size,
            iterations_completed=0,
            checksum=0,
            payload=bytes(RESULT_BUFFER_SIZE - 32),
        )

    return BenchmarkResultHeader(
        status=STATUS_SUCCESS,
        op_mode=op_mode,
        batch_size=batch_size,
        iterations_completed=total_iters,
        checksum=checksum,
        payload=bytes(payload),
    )


def calculate_benchmark_metrics(
    op_mode: int,
    batch_size: int,
    durations_us: List[float],
    bytes_per_op: int = 512,
) -> BenchmarkMetrics:
    """Calculates comprehensive high-throughput profiling statistics."""
    if not durations_us:
        raise ValueError("durations_us list must not be empty")

    n = len(durations_us)
    total_time = sum(durations_us)
    mean_val = total_time / n
    sorted_durations = sorted(durations_us)
    median_val = (
        sorted_durations[n // 2]
        if n % 2 == 1
        else (sorted_durations[n // 2 - 1] + sorted_durations[n // 2]) / 2.0
    )
    min_val = sorted_durations[0]
    max_val = sorted_durations[-1]

    variance = sum((x - mean_val) ** 2 for x in durations_us) / n if n > 1 else 0.0
    stddev_val = math.sqrt(variance)
    cv_percent = (stddev_val / mean_val * 100.0) if mean_val > 0 else 0.0

    latency_per_op_us = mean_val / batch_size if batch_size > 0 else mean_val
    ops_per_second = (batch_size / (mean_val * 1e-6)) if mean_val > 0 else 0.0
    throughput_mbs = (ops_per_second * bytes_per_op) / (1024 * 1024)

    return BenchmarkMetrics(
        op_mode=op_mode,
        batch_size=batch_size,
        total_wall_time_us=total_time,
        latency_per_op_us=latency_per_op_us,
        ops_per_second=ops_per_second,
        throughput_mbs=throughput_mbs,
        mean_us=mean_val,
        median_us=median_val,
        min_us=min_val,
        max_us=max_val,
        stddev_us=stddev_val,
        cv_percent=cv_percent,
    )
