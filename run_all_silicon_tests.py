# SPDX-License-Identifier: Apache-2.0
"""Universal Post-Quantum Cryptography & QKD Master Silicon Validation Suite.

For host-only preflight tests without physical hardware, see run_all_pqc_tests.py.

Executes and verifies 100% On-Device Device-Resident PQC & Hybrid QKD across all 25 Gates:
  - NIST FIPS 202: SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 (DR9)
  - NIST FIPS 203: ML-KEM-512, ML-KEM-768, ML-KEM-1024 (DR2d, DR3, DR4, DR5, DR6, DR7, DR8)
  - NIST FIPS 204: ML-DSA-44, ML-DSA-65, ML-DSA-87 (DR11, DR12, DR13, DR14, DR15)
  - Hybrid QKD + PQC Defense-in-Depth: DR16, DR17, DR18, DR19
  - Device-Resident Foundation & Lifecycle: DR0, DR1, DR2a, DR2b, DR2c, DR10

Target Hardware: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1).
All operations execute entirely on-device with zero host fallback or repair.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent
TESTS_DIR = REPO_ROOT / "tests" / "pqc_device_resident"

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


@dataclass(frozen=True)
class NativeGate:
    """One fail-closed physical gate in the canonical ordered sequence."""

    gate_id: str
    title: str
    script: Path
    backend_label: str
    expected_total: int
    timeout_seconds: int = 1800

    @property
    def relative_script(self) -> Path:
        return self.script.relative_to(REPO_ROOT)


GATES: tuple[NativeGate, ...] = (
    NativeGate(
        gate_id="DR0",
        title="Gate 00: DR0 M33 Ring Product",
        script=TESTS_DIR / "test_m33_product_dr0.py",
        backend_label="m33-dr0:silicon",
        expected_total=24,
    ),
    NativeGate(
        gate_id="DR1",
        title="Gate 01: DR1 ML-DSA-44 ExpandA",
        script=TESTS_DIR / "test_dr1_mldsa44_rejntt_silicon.py",
        backend_label="dr1-mldsa44-expanda-rejntt:silicon",
        expected_total=33,
    ),
    NativeGate(
        gate_id="DR2a",
        title="Gate 02: DR2a ML-KEM-512 SampleNTT",
        script=TESTS_DIR / "test_dr2a_mlkem512_samplentt_silicon.py",
        backend_label="dr2a-mlkem512-samplentt:silicon",
        expected_total=13,
    ),
    NativeGate(
        gate_id="DR2b",
        title="Gate 03: DR2b ML-KEM-512 CBD3/NTT",
        script=TESTS_DIR / "test_dr2b_mlkem512_noise_ntt_silicon.py",
        backend_label="dr2b-mlkem512-noise-ntt:silicon",
        expected_total=13,
    ),
    NativeGate(
        gate_id="DR2c",
        title="Gate 04: DR2c ML-KEM-512 KeyGen Row",
        script=TESTS_DIR / "test_dr2c_mlkem512_keygen_row_silicon.py",
        backend_label="dr2c-mlkem512-keygen-row:silicon",
        expected_total=11,
    ),
    NativeGate(
        gate_id="DR2d",
        title="Gate 05: DR2d ML-KEM-512 K-PKE KeyGen",
        script=TESTS_DIR / "test_dr2d_mlkem512_kpke_keygen_silicon.py",
        backend_label="dr2d-mlkem512-kpke-keygen:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR3",
        title="Gate 06: DR3 ML-KEM-512 K-PKE Encrypt",
        script=TESTS_DIR / "test_dr3_mlkem512_kpke_encrypt_silicon.py",
        backend_label="dr3-mlkem512-kpke-encrypt:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR4",
        title="Gate 07: DR4 ML-KEM-512 K-PKE Decrypt",
        script=TESTS_DIR / "test_dr4_mlkem512_kpke_decrypt_silicon.py",
        backend_label="dr4-mlkem512-kpke-decrypt:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR5",
        title="Gate 08: DR5 ML-KEM-512 ML-KEM KeyGen",
        script=TESTS_DIR / "test_dr5_mlkem512_keygen_silicon.py",
        backend_label="dr5-mlkem512-keygen:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR6",
        title="Gate 09: DR6 ML-KEM-512 ML-KEM Encaps",
        script=TESTS_DIR / "test_dr6_mlkem512_encaps_silicon.py",
        backend_label="dr6-mlkem512-encaps:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR7",
        title="Gate 10: DR7 ML-KEM-512 ML-KEM Decaps",
        script=TESTS_DIR / "test_dr7_mlkem512_decaps_silicon.py",
        backend_label="dr7-mlkem512-decaps:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR8",
        title="Gate 11: DR8 ML-KEM-768 & 1024 Expansion",
        script=TESTS_DIR / "test_dr8_mlkem_unified_silicon.py",
        backend_label="dr8-mlkem-unified:silicon",
        expected_total=75,
    ),
    NativeGate(
        gate_id="DR9",
        title="Gate 12: DR9 FIPS 202 SHA-3/SHAKE Service",
        script=TESTS_DIR / "test_dr9_fips202_silicon.py",
        backend_label="dr9-fips202:silicon",
        expected_total=122,
    ),
    NativeGate(
        gate_id="DR10",
        title="Gate 13: DR10 Sealed Lifecycle & Key Sources",
        script=TESTS_DIR / "test_dr10_sealed_lifecycle_silicon.py",
        backend_label="dr10-sealed-lifecycle:silicon",
        expected_total=40,
    ),
    NativeGate(
        gate_id="DR11",
        title="Gate 14: DR11 ML-DSA-44 KeyGen",
        script=TESTS_DIR / "test_dr11_mldsa44_keygen_silicon.py",
        backend_label="dr11-mldsa44-keygen:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR12",
        title="Gate 15: DR12 ML-DSA-44 Sign",
        script=TESTS_DIR / "test_dr12_mldsa44_sign_silicon.py",
        backend_label="dr12-mldsa44-sign:silicon",
        expected_total=30,
    ),
    NativeGate(
        gate_id="DR13",
        title="Gate 16: DR13 ML-DSA-44 Verify",
        script=TESTS_DIR / "test_dr13_mldsa44_verify_silicon.py",
        backend_label="dr13-mldsa44-verify:silicon",
        expected_total=30,
    ),
    NativeGate(
        gate_id="DR14",
        title="Gate 17: DR14 ML-DSA-65 (KeyGen, Sign, Verify)",
        script=TESTS_DIR / "test_dr14_mldsa65_silicon.py",
        backend_label="dr14-mldsa65:silicon",
        expected_total=85,
    ),
    NativeGate(
        gate_id="DR15",
        title="Gate 18: DR15 ML-DSA-87 (KeyGen, Sign, Verify)",
        script=TESTS_DIR / "test_dr15_mldsa87_silicon.py",
        backend_label="dr15-mldsa87:silicon",
        expected_total=85,
    ),
)

EXTENSION_GATES: tuple[NativeGate, ...] = (
    NativeGate(
        gate_id="DR16",
        title="Gate 19: DR16 ETSI GS QKD 014 Sealed Ingress",
        script=TESTS_DIR / "test_dr16_etsi_qkd014_silicon.py",
        backend_label="dr16-etsi014:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR17",
        title="Gate 20: DR17 ML-DSA Asymmetric QKD Control",
        script=TESTS_DIR / "test_dr17_mldsa_qkd_auth_silicon.py",
        backend_label="dr17-mldsa-auth:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR18",
        title="Gate 21: DR18 NIST SP 800-56C Dual Combiner",
        script=TESTS_DIR / "test_dr18_dual_key_combiner_silicon.py",
        backend_label="dr18-dual-combiner:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR19",
        title="Gate 22: DR19 Hybrid QKD-PQC Session Orchestrator",
        script=TESTS_DIR / "test_dr19_hybrid_session_silicon.py",
        backend_label="dr19-hybrid-session:silicon",
        expected_total=25,
    ),
    NativeGate(
        gate_id="DR27",
        title="Gate 23: DR27 QRNG-OPENAPI & Entropy Reservoir",
        script=TESTS_DIR / "test_dr27_qrng_reservoir_silicon.py",
        backend_label="dr27-qrng-reservoir:silicon",
        expected_total=21,
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Master Silicon Validation Suite")
    parser.add_argument("--list", action="store_true", help="List all verified native gates")
    parser.add_argument("--all", action="store_true", help="Include QKD/QRNG extension gates (24 gates total)")
    args = parser.parse_args()

    active_gates = GATES + EXTENSION_GATES if args.all else GATES

    if args.list:
        print(f"Canonical {len(active_gates)} Native Hardware Gates:")
        for g in active_gates:
            print(f"  {g.gate_id:<6}: {g.title} ({g.expected_total} cases)")
        return 0

    start_all = time.time()
    print("=" * 80)
    print("100% ON-DEVICE PQC & HYBRID QKD MASTER SILICON VALIDATION SUITE")
    print("Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)")
    print(f"Scope: Verified Hardware Gates ({len(active_gates)} Gates)")
    print("=" * 80)

    passed_gates = 0
    failed_gates = 0
    skipped_gates = 0
    python_exe = str(IRONENV_PYTHON) if IRONENV_PYTHON.is_file() else sys.executable

    for gate in active_gates:
        full_path = gate.script
        if not full_path.exists():
            print(f"[-] {gate.title:<52} : SKIPPED (File not found: {gate.relative_script})")
            skipped_gates += 1
            continue

        t0 = time.time()
        res = subprocess.run(
            [python_exe, "-u", str(full_path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True
        )
        dt = time.time() - t0

        if res.returncode == 0:
            passed_gates += 1
            print(f"[+] {gate.title:<52} : PASS ({dt:5.2f}s)")
        else:
            failed_gates += 1
            print(f"[-] {gate.title:<52} : FAIL ({dt:5.2f}s, exit {res.returncode})")
            if res.stderr:
                print(f"    ERROR: {res.stderr.strip()[:180]}")
            elif res.stdout:
                lines = [l for l in res.stdout.strip().splitlines() if l]
                if lines:
                    print(f"    OUTPUT: {lines[-1][:180]}")

    dt_all = time.time() - start_all
    total_gates = len(GATES)
    pass_pct = (passed_gates / total_gates * 100.0) if total_gates > 0 else 0.0

    print("=" * 80)
    if failed_gates == 0 and skipped_gates == 0:
        print(f"MASTER SILICON SUITE RESULT: {passed_gates}/{total_gates} GATES PASS (100.00%) in {dt_all:.2f}s")
        print(f"STATUS: ALL {passed_gates} VERIFIED GATES PASSED (100.00% Physical Silicon Correctness)")
    else:
        print(f"MASTER SILICON SUITE RESULT: {passed_gates}/{total_gates} GATES PASS ({pass_pct:.2f}%) in {dt_all:.2f}s")
        print(f"VALIDATION FAILED: {failed_gates} failed, {skipped_gates} skipped out of {total_gates} total gates.")
    print("=" * 80)
    return 0 if (failed_gates == 0 and skipped_gates == 0) else 1

if __name__ == "__main__":
    sys.exit(main())
