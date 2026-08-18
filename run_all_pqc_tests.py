#!/usr/bin/env python3
"""Run the explicit host-safe Phoenix NPU PQC validation suite.

The allowlist below contains contract, reference, and production-source checks
that may run on an ordinary host. This runner never selects ``*_silicon.py``,
loads the MLIR-AIE runtime, compiles an AIE program, or dispatches an NPU.
Physical gates remain separately documented research evidence.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

HOST_SAFE_TESTS = (
    "tests/test_pqc_device_residency_contract.py",
    "tests/pqc_device_resident/test_dr1_mldsa44_rejntt.py",
    "tests/pqc_device_resident/test_dr2_mlkem512_samplentt.py",
    "tests/pqc_device_resident/test_dr2b_mlkem512_noise_ntt.py",
    "tests/pqc_device_resident/test_dr2c_mlkem512_keygen_row.py",
    "tests/pqc_device_resident/test_dr2d_mlkem512_kpke_keygen.py",
    "tests/pqc_device_resident/test_dr2d_mlkem512_kpke_terminal_probe.py",
    "tests/pqc_device_resident/test_dr2d_mlkem512_kpke_sigma_prf_tap_contract.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run explicit host-safe PQC contract and reference tests. "
            "No hardware is accessed."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the allowlisted test plan without importing or running tests.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the allowlisted test paths and exit.",
    )
    return parser.parse_args()


def validate_allowlist() -> tuple[Path, ...]:
    paths = tuple(REPO_ROOT / relative for relative in HOST_SAFE_TESTS)
    missing = [path.relative_to(REPO_ROOT) for path in paths if not path.is_file()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise RuntimeError(
            f"host-safe test allowlist references missing files: {joined}"
        )
    forbidden = [path for path in paths if path.name.endswith("_silicon.py")]
    if forbidden:
        joined = ", ".join(str(path.relative_to(REPO_ROOT)) for path in forbidden)
        raise RuntimeError(
            f"host-safe test allowlist includes native gate(s): {joined}"
        )
    return paths


def print_plan(paths: tuple[Path, ...]) -> None:
    print("Phoenix NPU PQC host-safe test plan")
    print("Hardware access: disabled")
    for path in paths:
        print(f" - {path.relative_to(REPO_ROOT)}")
    print(f"Total: {len(paths)} test modules")


def run_test(path: Path) -> tuple[bool, float]:
    relative = path.relative_to(REPO_ROOT)
    print(f"\n=== {relative} ===")
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "-v", str(relative)],
        cwd=REPO_ROOT,
        check=False,
    )
    elapsed = time.perf_counter() - started
    state = "PASS" if result.returncode == 0 else "FAIL"
    print(f"--- {state}: {relative} ({elapsed:.2f}s) ---")
    return result.returncode == 0, elapsed


def main() -> int:
    args = parse_args()
    try:
        paths = validate_allowlist()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.list or args.dry_run:
        print_plan(paths)
        return 0

    print("Phoenix NPU PQC host-safe validation")
    print("Hardware access: disabled")
    results = [(path, *run_test(path)) for path in paths]
    failures = [path for path, passed, _ in results if not passed]

    print("\n=== SUMMARY ===")
    for path, passed, elapsed in results:
        state = "PASS" if passed else "FAIL"
        print(f"{state:4} {path.relative_to(REPO_ROOT)} ({elapsed:.2f}s)")
    print(
        f"Modules: {len(results)} | Passed: {len(results) - len(failures)} | Failed: {len(failures)}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
