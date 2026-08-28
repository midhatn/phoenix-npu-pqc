# SPDX-License-Identifier: Apache-2.0
"""Master runner for all device-resident PQC silicon tests on AMD Phoenix NPU."""
import subprocess
import os
import sys
from pathlib import Path

PYTHON_EXE = sys.executable

TESTS = [
    ("DR1 (ML-DSA-44 RejNTT)", "tests/pqc_device_resident/test_dr1_mldsa44_rejntt_silicon.py"),
    ("DR2a (ML-KEM-512 SampleNTT)", "tests/pqc_device_resident/test_dr2a_mlkem512_samplentt_silicon.py"),
    ("DR2b (ML-KEM-512 Noise+NTT)", "tests/pqc_device_resident/test_dr2b_mlkem512_noise_ntt_silicon.py"),
    ("DR2c (ML-KEM-512 KeyGen Row)", "tests/pqc_device_resident/test_dr2c_mlkem512_keygen_row_silicon.py"),
    ("DR2d (ML-KEM-512 K-PKE.KeyGen)", "tests/pqc_device_resident/test_dr2d_mlkem512_kpke_keygen_silicon.py"),
    ("DR3  (ML-KEM-512 K-PKE.Encrypt)", "tests/pqc_device_resident/test_dr3_mlkem512_kpke_encrypt_silicon.py"),
    ("DR4  (ML-KEM-512 K-PKE.Decrypt)", "tests/pqc_device_resident/test_dr4_mlkem512_kpke_decrypt_silicon.py"),
    ("DR5  (ML-KEM-512 ML-KEM.KeyGen)", "tests/pqc_device_resident/test_dr5_mlkem512_keygen_silicon.py"),
    ("DR6  (ML-KEM-512 ML-KEM.Encaps)", "tests/pqc_device_resident/test_dr6_mlkem512_encaps_silicon.py"),
    ("DR7  (ML-KEM-512 ML-KEM.Decaps)", "tests/pqc_device_resident/test_dr7_mlkem512_decaps_silicon.py"),
    ("DR8  (ML-KEM-768/1024 Expansion)", "tests/pqc_device_resident/test_dr8_mlkem_unified_silicon.py"),
    ("DR9  (Reusable FIPS 202 Service)", "tests/pqc_device_resident/test_dr9_fips202_silicon.py"),
    ("DR10 (Sealed Lifecycle Architecture)", "tests/pqc_device_resident/test_dr10_sealed_lifecycle_silicon.py"),
    ("DR11 (FIPS 204 ML-DSA-44 KeyGen)", "tests/pqc_device_resident/test_dr11_mldsa44_keygen_silicon.py"),
]

def main():
    print("=" * 80)
    print("MASTER SILICON REGRESSION SUITE - AMD PHOENIX NPU (XDNA1 / AIE2)")
    print("=" * 80)
    
    passed_milestones = 0
    
    for name, test_path in TESTS:
        print(f"\n>>> Running {name} on physical hardware...")
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
        res = subprocess.run([PYTHON_EXE, test_path], env=env)
        if res.returncode == 0:
            print(f">>> {name}: PASS")
            passed_milestones += 1
        else:
            print(f">>> {name}: FAILED (exit code {res.returncode})")
            sys.exit(1)
            
    print("\n" + "=" * 80)
    print(f"ALL {passed_milestones}/{len(TESTS)} PQC MILESTONES PASSED 100% BIT-EXACT ON PHYSICAL SILICON!")
    print("=" * 80)

if __name__ == "__main__":
    main()
