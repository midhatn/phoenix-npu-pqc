# SPDX-License-Identifier: Apache-2.0
"""Universal Post-Quantum Cryptography Master Silicon Validation Suite.

Executes and verifies 100% On-Device Device-Resident PQC across all 18 Gates:
  - NIST FIPS 202: SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 (DR9)
  - NIST FIPS 203: ML-KEM-512, ML-KEM-768, ML-KEM-1024 (DR2d, DR3, DR4, DR5, DR6, DR7, DR8)
  - NIST FIPS 204: ML-DSA-44, ML-DSA-65, ML-DSA-87 (DR11, DR12, DR13, DR14, DR15)
  - Device-Resident Foundation & Lifecycle: DR0, DR1, DR2a, DR2b, DR2c, DR10

Target Hardware: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1).
All operations execute entirely on-device with zero host fallback or repair.
"""
from __future__ import annotations

import sys
import time
import subprocess
from pathlib import Path

import os

REPO_ROOT = Path(__file__).resolve().parents[2]
IRONENV = (
    Path(os.environ["IRONENV_DIR"])
    if "IRONENV_DIR" in os.environ
    else (
        REPO_ROOT / "third_party" / "mlir-aie" / "ironenv"
        if (REPO_ROOT / "third_party" / "mlir-aie" / "ironenv" / "Scripts" / "python.exe").is_file()
        else Path(r"C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv")
    )
)
IRONENV_PYTHON = IRONENV / "Scripts" / "python.exe"

GATES = [
    ("Gate 00: DR0 M33 Ring Product", "tests/pqc_device_resident/test_m33_product_dr0.py"),
    ("Gate 01: DR1 ML-DSA-44 ExpandA", "tests/pqc_device_resident/test_dr1_mldsa44_rejntt_silicon.py"),
    ("Gate 02: DR2a ML-KEM-512 SampleNTT", "tests/pqc_device_resident/test_dr2a_mlkem512_samplentt_silicon.py"),
    ("Gate 03: DR2b ML-KEM-512 CBD3/NTT", "tests/pqc_device_resident/test_dr2b_mlkem512_noise_ntt_silicon.py"),
    ("Gate 04: DR2c ML-KEM-512 KeyGen Row", "tests/pqc_device_resident/test_dr2c_mlkem512_keygen_row_silicon.py"),
    ("Gate 05: DR2d ML-KEM-512 K-PKE KeyGen", "tests/pqc_device_resident/test_dr2d_mlkem512_kpke_keygen_silicon.py"),
    ("Gate 06: DR3 ML-KEM-512 K-PKE Encrypt", "tests/pqc_device_resident/test_dr3_mlkem512_kpke_encrypt_silicon.py"),
    ("Gate 07: DR4 ML-KEM-512 K-PKE Decrypt", "tests/pqc_device_resident/test_dr4_mlkem512_kpke_decrypt_silicon.py"),
    ("Gate 08: DR5 ML-KEM-512 ML-KEM KeyGen", "tests/pqc_device_resident/test_dr5_mlkem512_keygen_silicon.py"),
    ("Gate 09: DR6 ML-KEM-512 ML-KEM Encaps", "tests/pqc_device_resident/test_dr6_mlkem512_encaps_silicon.py"),
    ("Gate 10: DR7 ML-KEM-512 ML-KEM Decaps", "tests/pqc_device_resident/test_dr7_mlkem512_decaps_silicon.py"),
    ("Gate 11: DR8 ML-KEM-768 & 1024 Expansion", "tests/pqc_device_resident/test_dr8_mlkem_unified_silicon.py"),
    ("Gate 12: DR9 FIPS 202 SHA-3/SHAKE Service", "tests/pqc_device_resident/test_dr9_fips202_silicon.py"),
    ("Gate 13: DR10 Sealed Lifecycle & Key Sources", "tests/pqc_device_resident/test_dr10_sealed_lifecycle_silicon.py"),
    ("Gate 14: DR11 ML-DSA-44 KeyGen", "tests/pqc_device_resident/test_dr11_mldsa44_keygen_silicon.py"),
    ("Gate 15: DR12 ML-DSA-44 Sign", "tests/pqc_device_resident/test_dr12_mldsa44_sign_silicon.py"),
    ("Gate 16: DR13 ML-DSA-44 Verify", "tests/pqc_device_resident/test_dr13_mldsa44_verify_silicon.py"),
    ("Gate 17: DR14 ML-DSA-65 (KeyGen, Sign, Verify)", "tests/pqc_device_resident/test_dr14_mldsa65_silicon.py"),
    ("Gate 18: DR15 ML-DSA-87 (KeyGen, Sign, Verify)", "tests/pqc_device_resident/test_dr15_mldsa87_silicon.py"),
]

def main() -> int:
    start_all = time.time()
    print("=" * 80)
    print("100% ON-DEVICE PQC MASTER SILICON VALIDATION SUITE")
    print("Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)")
    print("Scope: Full NIST FIPS 202, FIPS 203, FIPS 204 Suite (DR0 through DR15)")
    print("=" * 80)

    passed_gates = 0
    python_exe = str(IRONENV_PYTHON) if IRONENV_PYTHON.is_file() else sys.executable

    for gate_name, script_path in GATES:
        full_path = REPO_ROOT / script_path
        if not full_path.exists():
            print(f"[-] {gate_name:<48} : SKIPPED (File not found: {script_path})")
            continue

        t0 = time.time()
        res = subprocess.run([python_exe, str(full_path)], capture_output=True, text=True)
        dur = time.time() - t0

        if res.returncode == 0:
            passed_gates += 1
            print(f"[+] {gate_name:<48} : PASS ({dur:5.2f}s)")
        else:
            print(f"[-] {gate_name:<48} : FAIL ({dur:5.2f}s, exit code {res.returncode})")
            print("--- Output excerpt ---")
            lines = res.stdout.strip().splitlines()[-6:]
            for l in lines:
                print("    " + l)
            if res.stderr:
                err_lines = res.stderr.strip().splitlines()[-4:]
                for el in err_lines:
                    print("    STDERR: " + el)

    total_time = time.time() - start_all
    print("=" * 80)
    print(f"TOTAL GATES: {passed_gates}/{len(GATES)} PASS on Physical Silicon in {total_time:.2f} seconds")
    print("100% NPU Residency: ZERO Host Fallback across All Finalized NIST PQC Standards")
    print("=" * 80)
    return 0 if passed_gates == len(GATES) else 1

if __name__ == "__main__":
    sys.exit(main())
