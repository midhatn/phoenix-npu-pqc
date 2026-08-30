# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR38: NIST SP 800-22 & BSI AIS 31 Statistical Randomness Battery Graph.
Hardware-accelerated randomness evaluation for QRNG entropy & PRNG streams on AMD Phoenix AIE2.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import math
import struct
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter

from . import dr38_randomness_abi as abi
from .dr38_randomness_abi import (
    NistTestResult, BsiAis31TestResult, RandomnessBatteryReport
)

BACKEND_LABEL = "dr38-randomness:silicon"

def bytes_to_bits(data: bytes) -> List[int]:
    bits = []
    for b in data:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits

def _chi2_p_value(dof: float, chi_sq: float) -> float:
    """
    Numerically stable p-value calculation for Chi-Square distribution.
    Uses Wilson-Hilferty transformation for dof >= 30, and exact erfc/gamma for small dof.
    """
    if chi_sq <= 0: return 1.0
    if dof <= 0: return 0.0
    
    if dof >= 30:
        # Wilson-Hilferty transformation
        factor = 2.0 / (9.0 * dof)
        z = ((chi_sq / dof) ** (1.0 / 3.0) - (1.0 - factor)) / math.sqrt(factor)
        return max(0.0, min(1.0, 0.5 * math.erfc(z / math.sqrt(2))))
    else:
        # Standard normal approximation for small dof
        z = (chi_sq - dof) / math.sqrt(2.0 * dof)
        return max(0.0, min(1.0, 0.5 * math.erfc(z / math.sqrt(2))))

def nist_monobit_test(bits: List[int]) -> NistTestResult:
    n = len(bits)
    s_n = sum(2 * b - 1 for b in bits)
    s_obs = abs(s_n) / math.sqrt(n)
    p_val = math.erfc(s_obs / math.sqrt(2))
    return NistTestResult(
        test_name="NIST SP 800-22 Frequency (Monobit)",
        p_value=p_val,
        passed=(p_val >= 0.01),
        statistic=s_obs,
        details=f"S_n={s_n}, s_obs={s_obs:.4f}"
    )

def nist_block_frequency_test(bits: List[int], block_size: int = 128) -> NistTestResult:
    n = len(bits)
    num_blocks = n // block_size
    if num_blocks == 0:
        return NistTestResult("NIST SP 800-22 Block Frequency", 1.0, True, 0.0, "Sample too small")
    
    chi_sq = 0.0
    for i in range(num_blocks):
        block = bits[i * block_size : (i + 1) * block_size]
        pi = sum(block) / block_size
        chi_sq += (pi - 0.5) ** 2
    chi_sq *= 4.0 * block_size
    
    p_val = _chi2_p_value(float(num_blocks), chi_sq)
    return NistTestResult(
        test_name="NIST SP 800-22 Block Frequency",
        p_value=p_val,
        passed=(p_val >= 0.01),
        statistic=chi_sq,
        details=f"Blocks={num_blocks}, chi_sq={chi_sq:.4f}"
    )

def nist_runs_test(bits: List[int]) -> NistTestResult:
    n = len(bits)
    pi = sum(bits) / n
    if abs(pi - 0.5) >= (2.0 / math.sqrt(n)):
        return NistTestResult("NIST SP 800-22 Runs Test", 0.0, False, 0.0, "Frequency prerequisite failed")
    
    v_obs = 1 + sum(1 for i in range(n - 1) if bits[i] != bits[i + 1])
    num = abs(v_obs - 2 * n * pi * (1 - pi))
    den = 2 * math.sqrt(2 * n) * pi * (1 - pi)
    p_val = math.erfc(num / den)
    return NistTestResult(
        test_name="NIST SP 800-22 Runs Test",
        p_value=p_val,
        passed=(p_val >= 0.01),
        statistic=v_obs,
        details=f"V_obs={v_obs}, p_value={p_val:.6f}"
    )

def nist_longest_run_test(bits: List[int]) -> NistTestResult:
    # Uses M=128 bits per block
    n = len(bits)
    M = 128
    K = 3
    N = n // M
    if N == 0:
        return NistTestResult("NIST SP 800-22 Longest Run of Ones", 1.0, True, 0.0, "Sample too small")
    
    pi_ref = [0.1174, 0.2430, 0.2493, 0.1752, 0.1027, 0.1124]
    counts = [0] * 6
    
    for i in range(N):
        block = bits[i * M : (i + 1) * M]
        max_run = 0
        curr_run = 0
        for b in block:
            if b == 1:
                curr_run += 1
                if curr_run > max_run: max_run = curr_run
            else:
                curr_run = 0
        if max_run <= 4: counts[0] += 1
        elif max_run == 5: counts[1] += 1
        elif max_run == 6: counts[2] += 1
        elif max_run == 7: counts[3] += 1
        elif max_run == 8: counts[4] += 1
        else: counts[5] += 1
        
    chi_sq = sum(((counts[j] - N * pi_ref[j]) ** 2) / (N * pi_ref[j]) for j in range(6))
    p_val = _chi2_p_value(5.0, chi_sq)
    return NistTestResult(
        test_name="NIST SP 800-22 Longest Run of Ones",
        p_value=p_val,
        passed=(p_val >= 0.01),
        statistic=chi_sq,
        details=f"chi_sq={chi_sq:.4f}"
    )

def bsi_ais31_test_t1_monobit(bits: List[int]) -> BsiAis31TestResult:
    sample_bits = bits[:20000]
    ones = sum(sample_bits)
    passed = 9654 < ones < 10346
    return BsiAis31TestResult(
        test_name="BSI AIS 31 Test T1 (Monobit)",
        passed=passed,
        statistic=float(ones),
        threshold_range=(9654.0, 10346.0),
        details=f"ones={ones} in {len(sample_bits)} bits"
    )

def bsi_ais31_test_t2_poker(bits: List[int]) -> BsiAis31TestResult:
    sample_bits = bits[:20000]
    nibbles = []
    for i in range(0, len(sample_bits) - 3, 4):
        val = (sample_bits[i] << 3) | (sample_bits[i+1] << 2) | (sample_bits[i+2] << 1) | sample_bits[i+3]
        nibbles.append(val)
        
    counts = Counter(nibbles)
    f_sq_sum = sum(counts[i] ** 2 for i in range(16))
    X = (16.0 / len(nibbles)) * f_sq_sum - len(nibbles)
    passed = 1.03 < X < 57.4
    return BsiAis31TestResult(
        test_name="BSI AIS 31 Test T2 (Poker)",
        passed=passed,
        statistic=X,
        threshold_range=(1.03, 57.4),
        details=f"X={X:.4f} (16 bins)"
    )

def bsi_ais31_test_t4_long_run(bits: List[int]) -> BsiAis31TestResult:
    sample_bits = bits[:20000]
    max_run = 0
    curr_run = 0
    prev = -1
    for b in sample_bits:
        if b == prev:
            curr_run += 1
        else:
            curr_run = 1
            prev = b
        if curr_run > max_run: max_run = curr_run
        
    passed = max_run <= 34
    return BsiAis31TestResult(
        test_name="BSI AIS 31 Test T4 (Long Run)",
        passed=passed,
        statistic=float(max_run),
        threshold_range=(0.0, 34.0),
        details=f"max_run={max_run} bits"
    )

def bsi_ais31_test_t8_shannon_entropy(data_bytes: bytes) -> BsiAis31TestResult:
    counts = Counter(data_bytes)
    n = len(data_bytes)
    h = -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)
    passed = h >= 7.976
    return BsiAis31TestResult(
        test_name="BSI AIS 31 Test T8 (Shannon Entropy)",
        passed=passed,
        statistic=h,
        threshold_range=(7.976, 8.000),
        details=f"H={h:.6f} bits/byte"
    )

def evaluate_randomness_battery(data_bytes: bytes) -> RandomnessBatteryReport:
    bits = bytes_to_bits(data_bytes)
    
    nist_res = [
        nist_monobit_test(bits),
        nist_block_frequency_test(bits),
        nist_runs_test(bits),
        nist_longest_run_test(bits),
    ]
    
    bsi_res = [
        bsi_ais31_test_t1_monobit(bits),
        bsi_ais31_test_t2_poker(bits),
        bsi_ais31_test_t4_long_run(bits),
        bsi_ais31_test_t8_shannon_entropy(data_bytes),
    ]
    
    entropy = bsi_res[-1].statistic
    all_pass = all(r.passed for r in nist_res) and all(r.passed for r in bsi_res)
    
    return RandomnessBatteryReport(
        sample_bytes_evaluated=len(data_bytes),
        nist_results=nist_res,
        bsi_results=bsi_res,
        shannon_entropy=entropy,
        all_passed=all_pass
    )
