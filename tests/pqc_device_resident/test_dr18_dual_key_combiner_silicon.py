# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR18: NIST SP 800-56C Dual-Key Combiner Silicon Validation Suite.
Backend: dr18-dual-key-combiner:silicon (AMD Phoenix AIE2 / XDNA1 Architecture).
"""

import secrets
import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phoenix_sdr_dsp.pqc.dr18_dual_key_combiner_graph import combine_keys_on_aie2
from phoenix_sdr_dsp.pqc import dr18_dual_key_combiner_abi as abi
from tests.pqc_device_resident.test_dr18_dual_key_combiner import compute_ref_k_final

def main():
    print("=" * 70)
    print("DR18: NIST SP 800-56C Dual-Key Combiner Silicon Validation")
    print("Backend: dr18-dual-key-combiner:silicon (AMD Phoenix AIE2)")
    print("Standards: NIST SP 800-56C Rev. 2, NIST SP 800-227, BSI TR-02102")
    print("=" * 70)

    test_cases = []

    # 1. Standard 256-bit Dual-Key Combination (15 cases)
    for i in range(1, 16):
        k_qkd = bytes([(i * 17 + j) % 256 for j in range(32)])
        k_pqc = bytes([(i * 31 + j) % 256 for j in range(32)])
        key_id = uuid.uuid4()
        epoch = 100 + i
        exp_k = compute_ref_k_final(k_qkd, k_pqc, key_id, epoch, 32)
        test_cases.append((f"dual_key_standard_{i:02d}", k_qkd, k_pqc, key_id, epoch, 32, exp_k))

    # 2. Dual-PRF Entropy Retention: Poisoned/Zeroed QKD (5 cases)
    for i in range(1, 6):
        k_qkd_zero = bytes(32) # Poisoned QKD optical channel
        k_pqc = secrets.token_bytes(32) # Valid ML-KEM secret
        key_id = uuid.uuid4()
        epoch = 200 + i
        exp_k = compute_ref_k_final(k_qkd_zero, k_pqc, key_id, epoch, 32)
        test_cases.append((f"entropy_retention_qkd_poisoned_{i:02d}", k_qkd_zero, k_pqc, key_id, epoch, 32, exp_k))

    # 3. Dual-PRF Entropy Retention: Compromised/Zeroed PQC (5 cases)
    for i in range(1, 6):
        k_qkd = secrets.token_bytes(32) # Valid QKD secret
        k_pqc_zero = bytes(32) # Broken PQC lattice
        key_id = uuid.uuid4()
        epoch = 300 + i
        exp_k = compute_ref_k_final(k_qkd, k_pqc_zero, key_id, epoch, 32)
        test_cases.append((f"entropy_retention_pqc_zeroed_{i:02d}", k_qkd, k_pqc_zero, key_id, epoch, 32, exp_k))

    # 4. High-Security 512-bit AES-XTS Key Extraction (5 cases)
    for i in range(1, 6):
        k_qkd = secrets.token_bytes(32)
        k_pqc = secrets.token_bytes(32)
        key_id = uuid.uuid4()
        epoch = 400 + i
        exp_k = compute_ref_k_final(k_qkd, k_pqc, key_id, epoch, 64)
        test_cases.append((f"dual_key_512bit_extraction_{i:02d}", k_qkd, k_pqc, key_id, epoch, 64, exp_k))

    total = len(test_cases)
    passed = 0
    print(f"Running {total} DR18 NIST SP 800-56C silicon test cases on AMD Phoenix...")

    t0 = time.time()
    for name, k_q, k_p, kid, ep, out_l, expected_k in test_cases:
        act_k, dt_ms = combine_keys_on_aie2(k_q, k_p, kid, ep, out_len=out_l)
        if act_k == expected_k and len(act_k) == out_l:
            passed += 1
        else:
            print(f"[FAIL] {name}: act_k={act_k.hex()[:16]}..., exp_k={expected_k.hex()[:16]}...")

    dt = time.time() - t0
    print("-" * 70)
    print(f"DR18 Physical Silicon Result: {passed}/{total} PASS ({passed/total*100:.2f}%) in {dt:.2f}s")
    if passed == total:
        print("[+] Gate 21: DR18 NIST SP 800-56C Dual-Key Combiner : PASS (100% Silicon Certified)")
        return 0
    else:
        print("[-] Gate 21: DR18 FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
