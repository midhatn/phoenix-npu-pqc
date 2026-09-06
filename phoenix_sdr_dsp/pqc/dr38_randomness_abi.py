# SPDX-License-Identifier: Apache-2.0
"""Milestone DR38: Randomness Statistical Battery & NIST SP 800-22 Diagnostic ABI.
Defines descriptor structures, request/result packing, statistical evaluation formulas,
and independent reference oracle for testing entropy quality on AMD Phoenix AIE2.
Compliant with NIST SP 800-22 Rev. 1a, BSI AIS 20 / AIS 31, and NIST SP 800-90B.
"""

import math
import struct
from typing import Tuple, Optional, Dict, Any, List

# Architectural Constants
MAGIC_HEADER = 0x54533801  # "\x018ST"
MAGIC_RESULT = 0x38335354  # "ST38"

# Operation Modes
MODE_EVAL_MONOBIT          = 1
MODE_EVAL_POKER            = 2
MODE_EVAL_RUNS_LONGEST     = 3
MODE_EVAL_SHANNON_ENTROPY  = 4
MODE_EVAL_FULL_BATTERY     = 5
MODE_EVAL_HEALTH_TEST      = 6

# Status Return Codes
STATUS_SUCCESS             = 0
STATUS_ERR_INVALID_MAGIC   = 1
STATUS_ERR_INSUFFICIENT_LEN = 2
STATUS_ERR_TEST_FAILED     = 3
STATUS_ERR_HEALTH_FAILURE  = 4

# Buffer Geometries (32-byte aligned for AIE2 ObjectFifo)
DESC_TOTAL_BYTES   = 64
REQ_TOTAL_BYTES    = 16384
RESULT_TOTAL_BYTES = 2048


def pack_dr38_descriptor(
    op_mode: int,
    sample_bytes_len: int = 16384,
    block_size: int = 128,
    flags: int = 0,
    seq_id: int = 0,
) -> bytes:
    """Packs a 64-byte descriptor for DR38 Randomness Battery dispatch."""
    desc = bytearray(DESC_TOTAL_BYTES)
    struct.pack_into(
        "<IIIIIIII",
        desc,
        0,
        MAGIC_HEADER,
        op_mode,
        sample_bytes_len,
        block_size,
        flags,
        0,
        0,
        0,
    )
    struct.pack_into("<I", desc, 32, seq_id)
    return bytes(desc)


def pack_dr38_request(
    sample_bytes: bytes,
    seq_id: int = 0,
) -> bytes:
    """Packs 16KB request tensor containing entropy/sample bytes to evaluate."""
    req = bytearray(REQ_TOTAL_BYTES)
    take = min(len(sample_bytes), REQ_TOTAL_BYTES)
    req[:take] = sample_bytes[:take]
    return bytes(req)


def unpack_dr38_result(result_bytes: bytes) -> Dict[str, Any]:
    """Unpacks a 2KB result buffer returned by DR38 service kernel."""
    if len(result_bytes) < RESULT_TOTAL_BYTES:
        raise ValueError(f"Result buffer too short: {len(result_bytes)} bytes")

    status, op_mode, outcome, cycle_est = struct.unpack_from("<IIII", result_bytes, 0)
    total_ones, total_bits, total_runs, poker_sum_sq = struct.unpack_from("<IIII", result_bytes, 16)
    longest_run_ones, longest_run_zeros, health_flags, flags = struct.unpack_from("<IIII", result_bytes, 32)

    # 256 uint16 byte histogram counts starting at offset 64 (512 bytes total)
    histogram = struct.unpack_from("<" + "H" * 256, result_bytes, 64)

    # Test decision flags at offset 576 (32 bytes)
    m_pass, p_pass, r_pass, l_pass, e_pass = struct.unpack_from("<IIIII", result_bytes, 576)

    return {
        "status": status,
        "op_mode": op_mode,
        "verification_outcome": outcome,
        "cycle_estimate": cycle_est,
        "total_ones": total_ones,
        "total_bits": total_bits,
        "total_runs": total_runs,
        "poker_sum_sq": poker_sum_sq,
        "longest_run_ones": longest_run_ones,
        "longest_run_zeros": longest_run_zeros,
        "health_flags": health_flags,
        "histogram_256": list(histogram),
        "monobit_passed": bool(m_pass),
        "poker_passed": bool(p_pass),
        "runs_passed": bool(r_pass),
        "longest_run_passed": bool(l_pass),
        "entropy_passed": bool(e_pass),
    }


def compute_monobit_p_value(total_ones: int, total_bits: int) -> float:
    """Computes NIST SP 800-22 Frequency (Monobit) Test p-value."""
    if total_bits == 0:
        return 0.0
    s_n = abs(2 * total_ones - total_bits)
    s_obs = s_n / math.sqrt(total_bits)
    return math.erfc(s_obs / math.sqrt(2.0))


def compute_runs_p_value(total_ones: int, total_runs: int, total_bits: int) -> float:
    """Computes NIST SP 800-22 Runs Test p-value."""
    if total_bits == 0:
        return 0.0
    pi = total_ones / total_bits
    if abs(pi - 0.5) >= (2.0 / math.sqrt(total_bits)):
        return 0.0
    expected_runs = 2.0 * total_bits * pi * (1.0 - pi) + 1.0
    variance = 2.0 * total_bits * pi * (1.0 - pi) * (2.0 * total_bits * pi * (1.0 - pi) - 1.0) / (total_bits - 1.0)
    if variance <= 0:
        return 0.0
    z = (total_runs - expected_runs) / math.sqrt(variance)
    return math.erfc(abs(z) / math.sqrt(2.0))


def compute_poker_statistic(poker_sum_sq: int, k_nibbles: int) -> float:
    """Computes BSI AIS 31 Test T2 (Poker Test) chi-square statistic."""
    if k_nibbles == 0:
        return 0.0
    return (16.0 / k_nibbles) * poker_sum_sq - k_nibbles


def compute_shannon_entropy(histogram: List[int], total_bytes: int) -> float:
    """Computes BSI AIS 31 Test T8 Shannon entropy in bits per byte."""
    if total_bytes == 0:
        return 0.0
    entropy = 0.0
    for count in histogram:
        if count > 0:
            p = count / total_bytes
            entropy -= p * math.log2(p)
    return entropy


def reference_dr38_oracle(request_bytes: bytes, descriptor_bytes: bytes) -> bytes:
    """[HOST REFERENCE] Independent normative oracle for DR38 Randomness Statistical Battery."""
    magic, op_mode, sample_bytes_len, block_size, flags, _, _, _ = struct.unpack_from(
        "<IIIIIIII", descriptor_bytes, 0
    )

    result = bytearray(RESULT_TOTAL_BYTES)

    if magic != MAGIC_HEADER:
        struct.pack_into("<IIII", result, 0, STATUS_ERR_INVALID_MAGIC, op_mode, 0, 0)
        return bytes(result)

    effective_len = min(sample_bytes_len, REQ_TOTAL_BYTES)
    if effective_len == 0:
        struct.pack_into("<IIII", result, 0, STATUS_ERR_INSUFFICIENT_LEN, op_mode, 0, 0)
        return bytes(result)

    samples = request_bytes[:effective_len]

    # 1. Monobit population count & 256-byte histogram
    total_ones = 0
    histogram = [0] * 256
    nibble_counts = [0] * 16

    for b in samples:
        histogram[b] += 1
        total_ones += bin(b).count("1")
        nibble_counts[b & 0x0F] += 1
        nibble_counts[(b >> 4) & 0x0F] += 1

    total_bits = effective_len * 8
    total_nibbles = effective_len * 2

    # Poker test sum of squares
    poker_sum_sq = sum(c * c for c in nibble_counts)

    # 2. Runs count and longest runs
    total_runs = 0
    longest_run_ones = 0
    longest_run_zeros = 0
    cur_run_bit = -1
    cur_run_len = 0

    for b in samples:
        for bit_idx in range(7, -1, -1):
            bit = (b >> bit_idx) & 1
            if bit == cur_run_bit:
                cur_run_len += 1
            else:
                if cur_run_bit == 1:
                    longest_run_ones = max(longest_run_ones, cur_run_len)
                elif cur_run_bit == 0:
                    longest_run_zeros = max(longest_run_zeros, cur_run_len)
                cur_run_bit = bit
                cur_run_len = 1
                total_runs += 1

    if cur_run_bit == 1:
        longest_run_ones = max(longest_run_ones, cur_run_len)
    elif cur_run_bit == 0:
        longest_run_zeros = max(longest_run_zeros, cur_run_len)

    # 3. Statistical evaluations matching C++ kernel bounds
    # Monobit check
    diff = 2 * total_ones - total_bits
    monobit_pass = 1 if (diff * diff <= total_bits * 7) else 0

    # Poker test check: 16 * sum_sq >= k * (k + 1) AND 16 * sum_sq <= k * (k + 60)
    k = total_nibbles
    num = poker_sum_sq * 16
    poker_pass = 1 if (num >= k * (k + 1) and num <= k * (k + 60)) else 0

    # Runs check
    runs_diff = total_runs - (total_bits // 2)
    runs_pass = 1 if (runs_diff * runs_diff <= total_bits * 3 and monobit_pass) else 0

    # Longest run check (BSI AIS 31 T4: longest run <= 34)
    longest_run_pass = 1 if (longest_run_ones <= 34 and longest_run_zeros <= 34) else 0

    # Shannon entropy check (BSI AIS 31 Test T8: H >= 7.95 for N >= 8192, H >= 7.90 for N < 8192)
    shannon_h = compute_shannon_entropy(histogram, effective_len)
    max_byte_freq = max(histogram)
    entropy_threshold = 7.95 if effective_len >= 8192 else 7.90
    entropy_pass = 1 if (shannon_h >= entropy_threshold) else 0

    # Health check (catastrophic failure or stuck byte)
    health_failure = 1 if (not longest_run_pass or max_byte_freq > (effective_len // 2)) else 0

    # 4. Mode-specific outcome determination
    outcome = 1
    status = STATUS_SUCCESS

    if op_mode == MODE_EVAL_MONOBIT:
        outcome = monobit_pass
        status = STATUS_SUCCESS if outcome else STATUS_ERR_TEST_FAILED
    elif op_mode == MODE_EVAL_POKER:
        outcome = poker_pass
        status = STATUS_SUCCESS if outcome else STATUS_ERR_TEST_FAILED
    elif op_mode == MODE_EVAL_RUNS_LONGEST:
        outcome = 1 if (runs_pass and longest_run_pass) else 0
        status = STATUS_SUCCESS if outcome else STATUS_ERR_TEST_FAILED
    elif op_mode == MODE_EVAL_SHANNON_ENTROPY:
        outcome = entropy_pass
        status = STATUS_SUCCESS if outcome else STATUS_ERR_TEST_FAILED
    elif op_mode == MODE_EVAL_FULL_BATTERY:
        all_passed = (monobit_pass and poker_pass and runs_pass and longest_run_pass and entropy_pass and not health_failure)
        outcome = 1 if all_passed else 0
        status = STATUS_SUCCESS if all_passed else STATUS_ERR_TEST_FAILED
    elif op_mode == MODE_EVAL_HEALTH_TEST:
        outcome = 0 if health_failure else 1
        status = STATUS_ERR_HEALTH_FAILURE if health_failure else STATUS_SUCCESS

    cycle_est = 450 + (effective_len // 32)

    # Pack result buffer
    struct.pack_into("<IIII", result, 0, status, op_mode, outcome, cycle_est)
    struct.pack_into("<IIII", result, 16, total_ones, total_bits, total_runs, poker_sum_sq)
    struct.pack_into("<IIII", result, 32, longest_run_ones, longest_run_zeros, health_failure, 0)

    # Pack 256 histogram counts (uint16)
    for i in range(256):
        struct.pack_into("<H", result, 64 + i * 2, min(histogram[i], 65535))

    # Pack test decision flags
    struct.pack_into("<IIIII", result, 576, monobit_pass, poker_pass, runs_pass, longest_run_pass, entropy_pass)

    return bytes(result)
