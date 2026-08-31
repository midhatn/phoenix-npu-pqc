# SPDX-License-Identifier: Apache-2.0
"""Ten deterministic non-ACVP regression inputs generated at runtime and compared against the unchanged independent host reference oracle.

This suite constructs 10 deterministic non-ACVP regression inputs at runtime using
SHA-256 derivations, computes expected 800-byte ek_pke and 768-byte dk_pke
buffers via the unchanged independent host reference oracle (dr2d_reference / FIPS 203 Section 5.1),
and executes the DR2d graph to verify complete buffer matching.
"""

import hashlib
import sys
import time
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr2d_mlkem512_kpke_keygen_graph as graph
from tests.pqc_device_resident.dr2d_reference import kpke_keygen_reference

NUM_DETERMINISTIC_CASES = 10
SEED_DOMAIN_PREFIX = b"dr2d_mlkem512_kpke_keygen_deterministic_seed_v1:"


class DeterministicCase(NamedTuple):
    case_index: int
    seed: bytes
    request_id: int


def generate_deterministic_cases(count: int = NUM_DETERMINISTIC_CASES) -> list[DeterministicCase]:
    cases = []
    for idx in range(count):
        d = hashlib.sha256(SEED_DOMAIN_PREFIX + str(idx).encode("utf-8")).digest()
        req_id = 0x90000000 + idx
        cases.append(DeterministicCase(case_index=idx, seed=d, request_id=req_id))
    return cases


def run_deterministic_regression_suite() -> int:
    cases = generate_deterministic_cases(NUM_DETERMINISTIC_CASES)
    selected_count = len(cases)
    executed_count = 0
    matching_count = 0
    failing_count = 0

    print("=" * 72)
    print(f"DR2D DETERMINISTIC NON-ACVP REGRESSION SUITE ({selected_count} CASES)")
    print("=" * 72)

    t0 = time.time()
    for case in cases:
        executed_count += 1
        oracle_ek, oracle_dk = kpke_keygen_reference(case.seed)
        actual_ek, actual_dk = graph.run_mlkem512_kpke_keygen(
            case.seed, case.request_id
        )

        ek_match = actual_ek == oracle_ek
        dk_match = actual_dk == oracle_dk
        match = ek_match and dk_match

        if match:
            matching_count += 1
            status = "PASS"
        else:
            failing_count += 1
            status = "FAIL"

        print(
            f"Case {case.case_index:02d} [req 0x{case.request_id:08x}]: "
            f"status={status} (ek_match={ek_match}, dk_match={dk_match})"
        )

    t1 = time.time()
    print("-" * 72)
    print(
        f"SUMMARY: Selected: {selected_count} | Executed: {executed_count} | "
        f"Matching: {matching_count} | Failing: {failing_count} (Elapsed: {t1-t0:.2f}s)"
    )
    print("=" * 72)

    if failing_count == 0 and matching_count == selected_count:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(run_deterministic_regression_suite())
