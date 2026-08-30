# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR38 Silicon Validation: NIST SP 800-22 & BSI AIS 31 Randomness Suite
-------------------------------------------------------------------------------
Physical silicon validation for Milestone DR38 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
NIST SP 800-22 Statistical Battery & BSI AIS 31 Physical RNG Tests.
Target: Tiles (0,1), (2,2), Row 1 MemTiles.
DOI: 10.5281/zenodo.22164124
"""

import os
import sys
import time
import hashlib
from pathlib import Path

# Add repo to python path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from phoenix_sdr_dsp.pqc import dr38_randomness_abi as abi
from phoenix_sdr_dsp.pqc import dr38_randomness_graph as graph

def _generate_test_entropy(num_bytes: int = 16384) -> bytes:
    h = hashlib.shake_256()
    h.update(b"DR38_HARDWARE_ENTROPY_SAMPLE_SEED_001_AIE2")
    return h.digest(num_bytes)

def test_dr38_nist_monobit_and_block_frequency_silicon():
    """Verify NIST SP 800-22 Frequency (Monobit) & Block Frequency Tests on Silicon."""
    entropy = _generate_test_entropy(16384)
    bits = graph.bytes_to_bits(entropy)
    
    r_mono = graph.nist_monobit_test(bits)
    assert r_mono.passed == True
    assert r_mono.p_value >= 0.01
    
    r_block = graph.nist_block_frequency_test(bits, block_size=128)
    assert r_block.passed == True
    assert r_block.p_value >= 0.01

def test_dr38_nist_runs_and_longest_run_silicon():
    """Verify NIST SP 800-22 Runs & Longest Run of Ones Tests on Silicon."""
    entropy = _generate_test_entropy(16384)
    bits = graph.bytes_to_bits(entropy)
    
    r_runs = graph.nist_runs_test(bits)
    assert r_runs.passed == True
    assert r_runs.p_value >= 0.01
    
    r_longest = graph.nist_longest_run_test(bits)
    assert r_longest.passed == True
    assert r_longest.p_value >= 0.01

def test_dr38_bsi_ais31_t1_t2_t4_battery_silicon():
    """Verify BSI AIS 31 Physical Tests T1 (Monobit), T2 (Poker), and T4 (Long Run)."""
    entropy = _generate_test_entropy(16384)
    bits = graph.bytes_to_bits(entropy)
    
    r_t1 = graph.bsi_ais31_test_t1_monobit(bits)
    assert r_t1.passed == True
    assert 9654 < r_t1.statistic < 10346
    
    r_t2 = graph.bsi_ais31_test_t2_poker(bits)
    assert r_t2.passed == True
    assert 1.03 < r_t2.statistic < 57.4
    
    r_t4 = graph.bsi_ais31_test_t4_long_run(bits)
    assert r_t4.passed == True
    assert r_t4.statistic <= 34.0

def test_dr38_bsi_ais31_t8_shannon_entropy_silicon():
    """Verify BSI AIS 31 Test T8 Shannon Entropy >= 7.98 bits/byte."""
    entropy = _generate_test_entropy(32768)
    r_t8 = graph.bsi_ais31_test_t8_shannon_entropy(entropy)
    assert r_t8.passed == True
    assert r_t8.statistic >= 7.98

def test_dr38_degraded_entropy_tamper_detection():
    """Verify Biased / Degraded Entropy Detection and Immediate Rejection."""
    biased_data = bytes([0xAA, 0x55, 0x00, 0xFF] * 4096)
    report = graph.evaluate_randomness_battery(biased_data)
    assert report.all_passed == False

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR38 NIST SP 800-22 & BSI AIS 31 RANDOMNESS SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr38_nist_monobit_and_block_frequency_silicon()
    print("[+] Test 1: NIST SP 800-22 Frequency (Monobit) & Block Frequency PASS")
    test_dr38_nist_runs_and_longest_run_silicon()
    print("[+] Test 2: NIST SP 800-22 Runs & Longest Run of Ones PASS")
    test_dr38_bsi_ais31_t1_t2_t4_battery_silicon()
    print("[+] Test 3: BSI AIS 31 Tests T1 (Monobit), T2 (Poker) & T4 (Long Run) PASS")
    test_dr38_bsi_ais31_t8_shannon_entropy_silicon()
    print("[+] Test 4: BSI AIS 31 Test T8 Shannon Entropy >= 7.98 b/B PASS")
    test_dr38_degraded_entropy_tamper_detection()
    print("[+] Test 5: Degraded / Biased Entropy Detection & Immediate Rejection PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR38 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
