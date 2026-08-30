# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR39: dudect Microarchitectural Constant-Time Side-Channel Leakage Verifier Graph.
Statistical TVLA (Welch's t-test) engine running over physical AIE2 hardware executions.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import time
import math
import random
import hashlib
from typing import Callable, Tuple, List, Dict, Any, Optional

from . import dr39_dudect_abi as abi
from .dr39_dudect_abi import (
    DUDECT_T_THRESHOLD, DudectDistribution, DudectWelchResult, SideChannelLeakageReport
)

from .dr8_mlkem768_keygen_graph import run_mlkem768_keygen
from .dr8_mlkem768_encaps_graph import run_mlkem768_encaps
from .dr8_mlkem768_decaps_graph import run_mlkem768_decaps

from .dr11_mldsa44_keygen_graph import run_mldsa44_keygen
from .dr12_mldsa44_sign_graph import run_mldsa44_sign
from .dr13_mldsa44_verify_graph import run_mldsa44_verify

from .dr37_hybrid_kem_graph import x25519_scalar_mult, x25519_base_mult

BACKEND_LABEL = "dr39-dudect:silicon"

def compute_welch_t(d0: DudectDistribution, d1: DudectDistribution) -> float:
    """Computes Welch's t-statistic between two Welford distributions."""
    if d0.count < 2 or d1.count < 2:
        return 0.0
    v0 = d0.variance()
    v1 = d1.variance()
    denom = math.sqrt((v0 / d0.count) + (v1 / d1.count))
    if denom == 0.0:
        return 0.0
    return (d0.mean - d1.mean) / denom

def run_tvla_test(
    primitive_name: str,
    fn_class0: Callable[[], Any],
    fn_class1: Callable[[], Any],
    iterations: int = 200
) -> DudectWelchResult:
    """
    Executes interleaved fixed-vs-random TVLA traces to eliminate environmental drift.
    """
    d0 = DudectDistribution()
    d1 = DudectDistribution()
    
    # Warm up hardware pipelines
    for _ in range(5):
        fn_class0()
        fn_class1()
        
    for i in range(iterations):
        # Randomize order to avoid branch predictor / cache order bias
        if random.random() < 0.5:
            t0 = time.perf_counter_ns()
            fn_class0()
            elapsed0 = time.perf_counter_ns() - t0
            d0.update(float(elapsed0))
            
            t1 = time.perf_counter_ns()
            fn_class1()
            elapsed1 = time.perf_counter_ns() - t1
            d1.update(float(elapsed1))
        else:
            t1 = time.perf_counter_ns()
            fn_class1()
            elapsed1 = time.perf_counter_ns() - t1
            d1.update(float(elapsed1))
            
            t0 = time.perf_counter_ns()
            fn_class0()
            elapsed0 = time.perf_counter_ns() - t0
            d0.update(float(elapsed0))
            
    t_stat = compute_welch_t(d0, d1)
    is_constant = abs(t_stat) < DUDECT_T_THRESHOLD
    
    return DudectWelchResult(
        primitive_name=primitive_name,
        t_statistic=t_stat,
        is_constant_time=is_constant,
        samples_class0=d0.count,
        samples_class1=d1.count,
        mean0=d0.mean,
        mean1=d1.mean,
        details=f"|t|={abs(t_stat):.3f} (Threshold={DUDECT_T_THRESHOLD})"
    )

def test_mlkem768_decaps_tvla(iterations: int = 100) -> DudectWelchResult:
    """TVLA test on ML-KEM-768 Decapsulation (Fixed CT vs Random CT)."""
    ek, dk = run_mlkem768_keygen(b"\x01" * 32, b"\x02" * 32)
    fixed_ct, _ = run_mlkem768_encaps(ek, b"\xAA" * 32)
    
    # Pre-generate random ciphertexts
    random_cts = []
    for i in range(iterations + 10):
        m_rand = hashlib.sha256(f"RAND_MSG_{i}".encode()).digest()
        c_rand, _ = run_mlkem768_encaps(ek, m_rand)
        random_cts.append(c_rand)
        
    idx = [0]
    def fn_class0():
        run_mlkem768_decaps(dk, fixed_ct)
        
    def fn_class1():
        c = random_cts[idx[0] % len(random_cts)]
        idx[0] += 1
        run_mlkem768_decaps(dk, c)
        
    return run_tvla_test("ML-KEM-768 Decapsulation", fn_class0, fn_class1, iterations=iterations)

def test_mldsa44_sign_tvla(iterations: int = 100) -> DudectWelchResult:
    """TVLA test on ML-DSA-44 Sign (Fixed Message vs Random Message)."""
    pk, sk = run_mldsa44_keygen(b"\x07" * 32)
    fixed_msg = b"FIXED_SIGNATURE_PAYLOAD_AIE2"
    
    rand_msgs = [hashlib.sha256(f"RAND_SIGN_{i}".encode()).digest() for i in range(iterations + 10)]
    idx = [0]
    
    def fn_class0():
        run_mldsa44_sign(sk, fixed_msg)
        
    def fn_class1():
        m = rand_msgs[idx[0] % len(rand_msgs)]
        idx[0] += 1
        run_mldsa44_sign(sk, m)
        
    return run_tvla_test("ML-DSA-44 Signature Generation", fn_class0, fn_class1, iterations=iterations)

def test_x25519_tvla(iterations: int = 200) -> DudectWelchResult:
    """TVLA test on Curve25519 Montgomery Ladder (Fixed Scalar vs Random Scalar)."""
    fixed_scalar = b"\x55" * 32
    base_u = (9).to_bytes(32, "little")
    
    rand_scalars = [hashlib.sha256(f"RAND_X25519_{i}".encode()).digest() for i in range(iterations + 10)]
    idx = [0]
    
    def fn_class0():
        x25519_scalar_mult(fixed_scalar, base_u)
        
    def fn_class1():
        s = rand_scalars[idx[0] % len(rand_scalars)]
        idx[0] += 1
        x25519_scalar_mult(s, base_u)
        
    return run_tvla_test("X25519 Montgomery Ladder", fn_class0, fn_class1, iterations=iterations)

def test_branchless_cmov_tvla(iterations: int = 500) -> DudectWelchResult:
    """TVLA test on Branchless Multiplexer CMOV."""
    a = 0x12345678
    b = 0x9ABCDEF0
    
    def cmov(cond: int, val_a: int, val_b: int) -> int:
        mask = -cond
        return (val_a & mask) | (val_b & ~mask)
        
    def fn_class0():
        # Condition 0
        return cmov(0, a, b)
        
    def fn_class1():
        # Condition 1
        return cmov(1, a, b)
        
    return run_tvla_test("Branchless CMOV Multiplexer", fn_class0, fn_class1, iterations=iterations)

def test_leaky_variable_time_benchmark(iterations: int = 300) -> DudectWelchResult:
    """
    Synthetic variable-time leak reference.
    Demonstrates that dudect correctly detects and fails when timing depends on secrets.
    """
    def fn_class0():
        # Secret 0: Fast path
        acc = 0
        for i in range(10): acc += i
        return acc
        
    def fn_class1():
        # Secret 1: Slow path (variable-time leak)
        acc = 0
        for i in range(150): acc += i
        return acc
        
    return run_tvla_test("Synthetic Variable-Time Leak (Reference)", fn_class0, fn_class1, iterations=iterations)
