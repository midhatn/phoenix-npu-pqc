# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator Silicon Validation Suite.
Target: AMD Phoenix AIE2 / XDNA1 Architecture (dr19-hybrid-session).
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr19_hybrid_session_orchestrator import run_hybrid_handshake_on_aie2

def main():
    print("=" * 75)
    print("DR19: Full-Duplex Hybrid QKD-PQC Session Orchestrator Silicon Validation")
    print("Target: AMD Phoenix AIE2 / XDNA1 (dr19-hybrid-session)")
    print("Standards: ETSI GS QKD 014, NIST FIPS 203/204, NIST SP 800-56C, IETF RFC 9370")
    print("=" * 75)

    test_configs = [
        # (Name, KEM, DSA, Count)
        ("Hybrid Session (ML-KEM-512 + ML-DSA-44)", "ML-KEM-512", "ML-DSA-44", 6),
        ("Hybrid Session (ML-KEM-768 + ML-DSA-44)", "ML-KEM-768", "ML-DSA-44", 5),
        ("Hybrid Session (ML-KEM-1024 + ML-DSA-44)", "ML-KEM-1024", "ML-DSA-44", 5),
        ("Hybrid High-Security (ML-KEM-768 + ML-DSA-65)", "ML-KEM-768", "ML-DSA-65", 4),
    ]

    total = sum(c[3] for c in test_configs)
    passed = 0
    test_idx = 1

    print(f"Executing {total} End-to-End Hybrid QKD-PQC handshakes on AMD Phoenix silicon...")

    t0 = time.time()
    for desc, kem, dsa, count in test_configs:
        for i in range(count):
            res = run_hybrid_handshake_on_aie2(kem_param=kem, dsa_param=dsa, epoch=1000 + test_idx)
            if res.is_authenticated and res.is_key_matched and res.zeroized_status == 0:
                passed += 1
                print(f"  [{test_idx:02d}/{total:02d}] {desc} #{i+1}: PASS (Authenticated & Key Matched in {res.total_latency_ms:.1f}ms, Zeroized: OK)")
            else:
                print(f"  [{test_idx:02d}/{total:02d}] {desc} #{i+1}: FAIL (auth={res.is_authenticated}, match={res.is_key_matched}, zero={res.zeroized_status})")
            test_idx += 1

    dt = time.time() - t0
    print("-" * 75)
    print(f"DR19 Physical Silicon Result: {passed}/{total} PASS ({passed/total*100:.2f}%) in {dt:.2f}s")
    if passed == total:
        print("[+] Gate 22: DR19 Full-Duplex Hybrid QKD-PQC Session Orchestrator : PASS (100% Silicon Certified)")
        return 0
    else:
        print("[-] Gate 22: DR19 FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
