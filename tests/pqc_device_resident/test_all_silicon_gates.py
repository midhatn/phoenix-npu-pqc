# SPDX-License-Identifier: Apache-2.0
"""Master Silicon Validation Suite (Physical Silicon Execution).

Executes and verifies fail-closed physical gates on AMD Phoenix NPU silicon:
  - NIST FIPS 202: SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, SHAKE256 (DR9)
  - NIST FIPS 203: ML-KEM-512, ML-KEM-768, ML-KEM-1024 (DR2d, DR3, DR4, DR5, DR6, DR7, DR8)
  - NIST FIPS 204: ML-DSA-44, ML-DSA-65, ML-DSA-87 (DR11, DR12, DR13, DR14, DR15)
  - Hybrid QKD + PQC Defense-in-Depth: DR16, DR17, DR18, DR19
  - Device-Resident Foundation & Lifecycle: DR0, DR1, DR2a, DR2b, DR2c, DR10

Target Hardware: AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1).
All physical gates require machine-readable per-case structured evidence records.
Child JSON records remain SELF_REPORTED_UNVERIFIED until corroborated by independent runtime verification.
"""
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from run_all_silicon_tests import (
    EXTENSION_GATES,
    GATES,
    STATUS_BLOCKED,
    STATUS_SELF_REPORTED_UNVERIFIED,
    execute_suite,
    get_ironenv_python,
    verify_execution_environment,
)


def main() -> int:
    active_gates = GATES + EXTENSION_GATES
    total_cases_selected = sum(g.expected_total for g in active_gates)

    print("=" * 80)
    print("MASTER SILICON VALIDATION SUITE (PHYSICAL SILICON EXECUTION)")
    print("Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)")
    print(f"Scope: {len(active_gates)} Native Hardware Gates ({total_cases_selected} Cases)")
    print("=" * 80)

    env_ok, env_msg = verify_execution_environment()
    if not env_ok:
        print(f"INFRASTRUCTURE FAILURE: {env_msg}", file=sys.stderr)
        return 1

    python_exe = get_ironenv_python()
    results, dt_all = execute_suite(active_gates, python_exe, REPO_ROOT)

    total_gates = len(active_gates)
    passed_gates = sum(1 for r in results if r.success)
    unverified_gates = sum(1 for r in results if r.status == STATUS_SELF_REPORTED_UNVERIFIED)
    blocked_gates = sum(1 for r in results if r.status == STATUS_BLOCKED)
    failed_gates = total_gates - passed_gates - unverified_gates - blocked_gates

    total_cases_passed = sum(r.cases_passed for r in results)
    total_cases_unverified = sum(r.cases_unverified for r in results)
    total_cases_failed = sum(r.cases_failed for r in results)
    total_cases_blocked = sum(r.cases_selected for r in results if r.status == STATUS_BLOCKED)

    print("=" * 80)
    print(f"MASTER SILICON SUITE RESULT: {passed_gates}/{total_gates} GATES PHYSICALLY VERIFIED ({dt_all:.2f}s)")
    print(f"Gate Status Breakdown: {unverified_gates} unverified, {blocked_gates} blocked, {failed_gates} failed")
    print(
        f"Case Status Breakdown: {total_cases_passed} verified passed, {total_cases_unverified} unverified claims, "
        f"{total_cases_failed} failed, {total_cases_blocked} blocked of {total_cases_selected} selected."
    )
    print("NOTICE: Physical silicon verification is BLOCKED pending trusted dispatch and KAT-output corroboration.")
    print("=" * 80)

    return 0 if (
        failed_gates == 0
        and unverified_gates == 0
        and blocked_gates == 0
        and total_gates > 0
        and total_cases_passed == total_cases_selected
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
