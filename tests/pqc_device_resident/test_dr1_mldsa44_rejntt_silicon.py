"""Native-only Phoenix gate for the narrow DR1 ML-DSA-44 ExpandA/RejNTT graph.

This module is a physical gate only. It reuses the exact 33-case corpus and the
independent ``hashlib``-based oracle already reviewed in
``tests/pqc_device_resident/test_dr1_mldsa44_rejntt.py`` and dispatches every
case through the production DR1 graph on Phoenix silicon. There is no host
execution backend, no fallback backend, and no skip path. The host computes an
independent oracle only to verify the terminal result returned by the NPU. If
the native IRON/XRT/Phoenix runtime is unavailable the gate reports
``unavailable`` and exits non-zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import dr1_mldsa44_rejntt_graph as graph
from tests.pqc_device_resident.dr1_reference import expanda_rejntt_reference
from tests.pqc_device_resident.test_dr1_mldsa44_rejntt import (
    DR1_CORPUS_SHA256,
    FINGERPRINT_BY_LABEL,
    PRE_SILICON_CORPUS,
    _coefficient_digest,
    pre_silicon_corpus_sha256,
)

EXPECTED_TOTAL = len(PRE_SILICON_CORPUS)


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR1 - ML-DSA-44 ExpandA rejection-sampling NTT")
    try:
        graph.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - a native-only gate must fail closed
        print(
            "Backend: dr1-mldsa44-expanda-rejntt:unavailable "
            f"({type(exc).__name__}: {exc})"
        )
        print(
            "UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran."
        )
        return 2

    actual_corpus_sha256 = pre_silicon_corpus_sha256()
    if actual_corpus_sha256 != DR1_CORPUS_SHA256:
        print(
            "CORPUS ERROR: serialized DR1 corpus SHA-256 "
            f"{actual_corpus_sha256} != frozen {DR1_CORPUS_SHA256}"
        )
        return 1

    print(f"Backend: {graph.BACKEND_LABEL}")
    print(f"Corpus SHA-256: {DR1_CORPUS_SHA256}")
    passed = 0
    for case in PRE_SILICON_CORPUS:
        expected = expanda_rejntt_reference(case.rho, case.j, case.i)
        try:
            actual = graph.run_mldsa44_expanda_rejntt(
                case.rho, case.j, case.i, case.request_id
            )
        except Exception as exc:  # noqa: BLE001 - a native error is a gate failure
            print(f"  {case.label:<28} ERROR ({type(exc).__name__}: {exc})")
            continue
        if (
            not expected.limit_exceeded
            and actual == list(expected.coefficients)
            and _coefficient_digest(actual) == FINGERPRINT_BY_LABEL[case.label]
        ):
            passed += 1
            print(f"  {case.label:<28} PASS")
        else:
            print(f"  {case.label:<28} FAIL")

    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    print("-" * 72)
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")
    print("=" * 72)
    return 0 if passed == EXPECTED_TOTAL else 1


if __name__ == "__main__":
    raise SystemExit(_run_native_gate())
