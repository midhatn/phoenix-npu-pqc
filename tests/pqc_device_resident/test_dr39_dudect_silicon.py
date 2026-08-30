# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR39 Silicon Validation: dudect Microarchitectural Side-Channel TVLA Verifier
---------------------------------------------------------------------------------------
Physical silicon validation for Milestone DR39 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Welch's t-test TVLA evaluating constant-time invariance (|t| < 4.5, p > 0.001).
Target: Tiles (1,2), (2,0..2,3), (3,2).
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
from pathlib import Path

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr39_dudect_abi as abi
from phoenix_sdr_dsp.pqc import dr39_dudect_graph as graph

def test_dr39_branchless_cmov_constant_time():
    """Verify Branchless CMOV Multiplexer Constant-Time TVLA (|t| < 4.5)."""
    res = graph.test_branchless_cmov_tvla(iterations=300)
    assert res.is_constant_time == True
    assert abs(res.t_statistic) < abi.DUDECT_T_THRESHOLD

def test_dr39_x25519_montgomery_ladder_constant_time():
    """Verify Curve25519 Montgomery Ladder Constant-Time TVLA (|t| < 4.5)."""
    res = graph.test_x25519_tvla(iterations=100)
    assert res.is_constant_time == True
    assert abs(res.t_statistic) < abi.DUDECT_T_THRESHOLD

def test_dr39_mlkem768_decaps_constant_time():
    """Verify ML-KEM-768 Decapsulation Constant-Time TVLA on AIE2 Silicon (|t| < 4.5)."""
    res = graph.test_mlkem768_decaps_tvla(iterations=25)
    assert res.is_constant_time == True
    assert abs(res.t_statistic) < abi.DUDECT_T_THRESHOLD

def test_dr39_mldsa44_sign_constant_time():
    """Verify ML-DSA-44 Signature Generation Constant-Time TVLA on AIE2 Silicon (|t| < 4.5)."""
    res = graph.test_mldsa44_sign_tvla(iterations=25)
    assert res.is_constant_time == True
    assert abs(res.t_statistic) < abi.DUDECT_T_THRESHOLD

def test_dr39_synthetic_variable_time_leak_detection():
    """Verify dudect Sensitivity: Correctly detects and flags variable-time leakage (|t| >= 4.5)."""
    res = graph.test_leaky_variable_time_benchmark(iterations=150)
    assert res.is_constant_time == False
    assert abs(res.t_statistic) >= abi.DUDECT_T_THRESHOLD

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR39 DUDECT CONSTANT-TIME SIDE-CHANNEL LEAKAGE SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr39_branchless_cmov_constant_time()
    print("[+] Test 1: Branchless CMOV Multiplexer Constant-Time TVLA PASS (|t| < 4.5)")
    test_dr39_x25519_montgomery_ladder_constant_time()
    print("[+] Test 2: Curve25519 Montgomery Ladder Constant-Time TVLA PASS (|t| < 4.5)")
    test_dr39_mlkem768_decaps_constant_time()
    print("[+] Test 3: ML-KEM-768 Decapsulation Constant-Time TVLA PASS (|t| < 4.5)")
    test_dr39_mldsa44_sign_constant_time()
    print("[+] Test 4: ML-DSA-44 Sign Constant-Time TVLA PASS (|t| < 4.5)")
    test_dr39_synthetic_variable_time_leak_detection()
    print("[+] Test 5: Synthetic Variable-Time Leakage Correctly Detected PASS (|t| >= 4.5)")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR39 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
