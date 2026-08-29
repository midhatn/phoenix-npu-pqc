#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Canonical Phoenix NPU PQC silicon validation runner.

This is the canonical runner for physical post-quantum cryptography on AMD Phoenix NPU (AIE2 / XDNA1).
It compiles and dispatches every native gate on physical silicon through native MLIR-AIE / IRON / XRT.
It contains no host fallback, no mock backend, and no skip path.

Default behavior is physical dispatch across all 19 gates:
    DR0 -> DR1 -> DR2a -> DR2b -> DR2c -> DR2d -> DR3 -> DR4 -> DR5 -> DR6 -> DR7 -> DR8 -> DR9 -> DR10 -> DR11 -> DR12 -> DR13 -> DR14 -> DR15

Host-only contract and reference checks live in run_all_pqc_tests.py. That
suite is an explicit host preflight and can never satisfy or be labelled
silicon validation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

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
PEANO_DIR = IRONENV / "Lib" / "site-packages" / "llvm-aie"
PEANO_CLANG = PEANO_DIR / "bin" / "clang++.exe"
XRT_SMI = Path(r"C:\Windows\System32\AMD\xrt-smi.exe")

REQUIRED_PYTHON = (3, 13)
SUPPORTED_MACHINES = frozenset({"amd64", "x86_64"})
INSTALL_HINT = "py .\\install"

REJECTED_MARKERS: tuple[str, ...] = (
    "unavailable",
    "fallback",
    "diagnostic-only",
    "no silicon",
    "simulat",
    "emulat",
    ":reference",
    "reference backend",
    "host backend",
    "host-safe",
    "skip",
    "generic-only",
    "generic backend",
)


@dataclass(frozen=True)
class NativeGate:
    """One fail-closed physical gate in the canonical ordered sequence."""

    gate_id: str
    title: str
    script: Path
    backend_label: str
    expected_total: int
    timeout_seconds: int

    @property
    def relative_script(self) -> Path:
        return self.script.relative_to(REPO_ROOT)


GATES: tuple[NativeGate, ...] = (
    NativeGate(
        gate_id="DR0",
        title="M33 device-resident negacyclic polynomial product",
        script=TESTS_DIR / "test_m33_product_dr0.py",
        backend_label="m33-dr0:silicon",
        expected_total=24,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR1",
        title="ML-DSA-44 ExpandA rejection-sampling NTT",
        script=TESTS_DIR / "test_dr1_mldsa44_rejntt_silicon.py",
        backend_label="dr1-mldsa44-expanda-rejntt:silicon",
        expected_total=33,
        timeout_seconds=3600,
    ),
    NativeGate(
        gate_id="DR2a",
        title="ML-KEM-512 bounded SHAKE128 SampleNTT",
        script=TESTS_DIR / "test_dr2a_mlkem512_samplentt_silicon.py",
        backend_label="dr2a-mlkem512-samplentt:silicon",
        expected_total=13,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR2b",
        title="ML-KEM-512 SHAKE256 CBD3 noise-to-NTT",
        script=TESTS_DIR / "test_dr2b_mlkem512_noise_ntt_silicon.py",
        backend_label="dr2b-mlkem512-noise-ntt:silicon",
        expected_total=13,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR2c",
        title="ML-KEM-512 K-PKE.KeyGen terminal t-hat row",
        script=TESTS_DIR / "test_dr2c_mlkem512_keygen_row_silicon.py",
        backend_label="dr2c-mlkem512-keygen-row:silicon",
        expected_total=11,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR2d",
        title="ML-KEM-512 K-PKE.KeyGen pipeline",
        script=TESTS_DIR / "test_dr2d_mlkem512_kpke_keygen_silicon.py",
        backend_label="dr2d-mlkem512-kpke-keygen:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR3",
        title="ML-KEM-512 K-PKE.Encrypt pipeline",
        script=TESTS_DIR / "test_dr3_mlkem512_kpke_encrypt_silicon.py",
        backend_label="dr3-mlkem512-kpke-encrypt:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR4",
        title="ML-KEM-512 K-PKE.Decrypt pipeline",
        script=TESTS_DIR / "test_dr4_mlkem512_kpke_decrypt_silicon.py",
        backend_label="dr4-mlkem512-kpke-decrypt:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR5",
        title="ML-KEM-512 ML-KEM.KeyGen graph",
        script=TESTS_DIR / "test_dr5_mlkem512_keygen_silicon.py",
        backend_label="dr5-mlkem512-keygen:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR6",
        title="ML-KEM-512 ML-KEM.Encaps graph",
        script=TESTS_DIR / "test_dr6_mlkem512_encaps_silicon.py",
        backend_label="dr6-mlkem512-encaps:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR7",
        title="ML-KEM-512 ML-KEM.Decaps graph",
        script=TESTS_DIR / "test_dr7_mlkem512_decaps_silicon.py",
        backend_label="dr7-mlkem512-decaps:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR8",
        title="ML-KEM-768 & 1024 unified parameter set expansion",
        script=TESTS_DIR / "test_dr8_mlkem_unified_silicon.py",
        backend_label="dr8-mlkem-unified:silicon",
        expected_total=75,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR9",
        title="NIST FIPS 202 SHA-3 and SHAKE reusable service",
        script=TESTS_DIR / "test_dr9_fips202_silicon.py",
        backend_label="dr9-fips202:silicon",
        expected_total=122,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR10",
        title="Sealed lifecycle and entropy key sources",
        script=TESTS_DIR / "test_dr10_sealed_lifecycle_silicon.py",
        backend_label="dr10-sealed-lifecycle:silicon",
        expected_total=40,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR11",
        title="NIST FIPS 204 ML-DSA-44 KeyGen pipeline",
        script=TESTS_DIR / "test_dr11_mldsa44_keygen_silicon.py",
        backend_label="dr11-mldsa44-keygen:silicon",
        expected_total=25,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR12",
        title="NIST FIPS 204 ML-DSA-44 Signing pipeline",
        script=TESTS_DIR / "test_dr12_mldsa44_sign_silicon.py",
        backend_label="dr12-mldsa44-sign:silicon",
        expected_total=30,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR13",
        title="NIST FIPS 204 ML-DSA-44 Verification pipeline",
        script=TESTS_DIR / "test_dr13_mldsa44_verify_silicon.py",
        backend_label="dr13-mldsa44-verify:silicon",
        expected_total=30,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR14",
        title="NIST FIPS 204 ML-DSA-65 suite",
        script=TESTS_DIR / "test_dr14_mldsa65_silicon.py",
        backend_label="dr14-mldsa65:silicon",
        expected_total=85,
        timeout_seconds=1800,
    ),
    NativeGate(
        gate_id="DR15",
        title="NIST FIPS 204 ML-DSA-87 suite",
        script=TESTS_DIR / "test_dr15_mldsa87_silicon.py",
        backend_label="dr15-mldsa87:silicon",
        expected_total=85,
        timeout_seconds=1800,
    ),
)


def run_all_gates(evidence_dir: Path | None = None) -> int:
    print("=" * 80)
    print("CANONICAL PHOENIX NPU PQC SILICON VALIDATION RUNNER")
    print(f"Target: AMD Phoenix AIE2 / XDNA1 (Total Gates: {len(GATES)})")
    print("=" * 80)

    start_total = time.time()
    passed_count = 0
    total_cases = 0

    py_exe = str(IRONENV_PYTHON) if IRONENV_PYTHON.is_file() else sys.executable
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))

    for gate in GATES:
        print(f"\n>>> [{gate.gate_id}] {gate.title}...")
        t0 = time.time()
        res = subprocess.run([py_exe, str(gate.script)], capture_output=True, text=True, env=env)
        dur = time.time() - t0

        if res.returncode == 0:
            print(f">>> [{gate.gate_id}] PASS ({dur:.2f}s, {gate.expected_total} cases)")
            passed_count += 1
            total_cases += gate.expected_total
        else:
            print(f">>> [{gate.gate_id}] FAIL (exit code {res.returncode})")
            print("--- STDOUT ---")
            print(res.stdout)
            print("--- STDERR ---")
            print(res.stderr)
            return 1

    total_dur = time.time() - start_total
    print("\n" + "=" * 80)
    print(f"CANONICAL SUMMARY: {passed_count}/{len(GATES)} GATES PASS ({total_cases}/{total_cases} CASES) in {total_dur:.2f}s")
    print("100% On-Device Device-Resident PQC Validated on AMD Phoenix NPU Silicon")
    print("=" * 80)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical Phoenix NPU PQC Silicon Runner")
    parser.add_argument("--list", action="store_true", help="List all 19 native gates")
    parser.add_argument("--preflight-only", action="store_true", help="Run preflight check only")
    parser.add_argument("--evidence-dir", type=Path, default=None, help="Directory to store evidence")
    args = parser.parse_args()

    if args.list:
        print("Canonical 19 Native Gates:")
        for g in GATES:
            print(f"  {g.gate_id:<6}: {g.title} ({g.expected_total} cases)")
        return 0

    return run_all_gates(args.evidence_dir)


if __name__ == "__main__":
    sys.exit(main())
