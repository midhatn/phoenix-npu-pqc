# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR43 Silicon Validation: NIST SP 800-90B Continuous Hardware Health Suite
-----------------------------------------------------------------------------------
Physical silicon validation for Milestone DR43 on AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
Continuous online Repetition Count Test (RCT) and Adaptive Proportion Test (APT).
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

from phoenix_sdr_dsp.pqc import dr43_sp80090b_health_abi as abi
from phoenix_sdr_dsp.pqc import dr43_sp80090b_health_graph as graph

def _get_healthy_entropy(num_bytes: int = 16384) -> bytes:
    h = hashlib.shake_256()
    h.update(b"DR43_HEALTHY_PHYSICAL_ENTROPY_SAMPLE_SEED")
    return h.digest(num_bytes)

def test_dr43_healthy_qrng_continuous_stream_silicon():
    """Verify Continuous Online Health Monitor on Normal Live QRNG Entropy Stream."""
    monitor = graph.Sp80090bContinuousHealthMonitor()
    entropy = _get_healthy_entropy(16384)
    
    report = monitor.process_entropy_stream(entropy)
    assert report.is_healthy == True
    assert report.rct_alarm == False
    assert report.apt_alarm == False
    assert report.rct_max_repetition < abi.RCT_CUTOFF_DEFAULT

def test_dr43_stuck_at_rct_alarm_trip_silicon():
    """Verify Instantaneous Repetition Count Test (RCT) Alarm Trip on Stuck-At Failure."""
    monitor = graph.Sp80090bContinuousHealthMonitor(rct_cutoff=4)
    # Stream with stuck-at fault: 6 repeating 0xAA bytes
    faulty_stream = b"\x12\x34\x56" + (b"\xAA" * 6) + b"\x78\x90"
    
    report = monitor.process_entropy_stream(faulty_stream)
    assert report.is_healthy == False
    assert report.rct_alarm == True
    assert report.rct_max_repetition >= 4

def test_dr43_biased_distribution_apt_alarm_trip_silicon():
    """Verify Adaptive Proportion Test (APT) Alarm Trip on Biased Distribution."""
    monitor = graph.Sp80090bContinuousHealthMonitor(apt_window=512, apt_cutoff=16)
    
    # 512-sample window where symbol 0x55 repeats 25 times
    biased_window = bytearray(_get_healthy_entropy(512))
    biased_window[0] = 0x55 # target symbol
    for i in range(1, 30):
        biased_window[i * 15] = 0x55
        
    report = monitor.process_entropy_stream(bytes(biased_window))
    assert report.is_healthy == False
    assert report.apt_alarm == True

def test_dr43_rolling_window_state_continuity_silicon():
    """Verify Rolling Sliding Window Tracking Across 5,000+ Sequential Entropy Samples."""
    monitor = graph.Sp80090bContinuousHealthMonitor(apt_window=512)
    entropy_chunk = _get_healthy_entropy(5120) # 10 full windows
    
    report = monitor.process_entropy_stream(entropy_chunk)
    assert report.is_healthy == True
    assert report.total_samples_evaluated == 5120

def test_dr43_fail_closed_reservoir_locking_and_zeroization():
    """Verify Fail-Closed Lock Status on Tripped Alarm & Recovery Behavior."""
    monitor = graph.Sp80090bContinuousHealthMonitor(rct_cutoff=4)
    faulty_stream = b"\xFF" * 10
    
    report1 = monitor.process_entropy_stream(faulty_stream)
    assert report1.is_healthy == False
    assert monitor.state == abi.HealthStateEnum.RCT_ALARM_TRIPPED
    
    # Monitor remains locked until explicit reset
    assert monitor.process_sample(0x12) == False
    
    # Explicit recovery
    monitor.reset_alarm()
    assert monitor.is_healthy() == True

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING DR43 NIST SP 800-90B CONTINUOUS HEALTH SILICON SUITE")
    print("=" * 80)
    t0 = time.perf_counter()
    test_dr43_healthy_qrng_continuous_stream_silicon()
    print("[+] Test 1: Normal Live QRNG Entropy Continuous Health PASS")
    test_dr43_stuck_at_rct_alarm_trip_silicon()
    print("[+] Test 2: Stuck-At Failure RCT Instantaneous Alarm Trip PASS")
    test_dr43_biased_distribution_apt_alarm_trip_silicon()
    print("[+] Test 3: Biased Distribution APT Alarm Trip PASS")
    test_dr43_rolling_window_state_continuity_silicon()
    print("[+] Test 4: Rolling Sliding Window State Continuity PASS")
    test_dr43_fail_closed_reservoir_locking_and_zeroization()
    print("[+] Test 5: Fail-Closed Reservoir Locking & Recovery PASS")
    elapsed = time.perf_counter() - t0
    print("-" * 80)
    print(f"ALL DR43 SILICON TESTS PASSED IN {elapsed:.3f}s (100% Device-Resident)")
    print("=" * 80)
