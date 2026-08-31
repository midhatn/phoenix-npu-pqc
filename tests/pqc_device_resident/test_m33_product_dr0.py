"""DR0 device-resident terminal-product gate and off-hardware reference tests.

Running this file directly is intentionally a native-only physical gate.  Its
unit tests remain useful on ordinary hosts; the script entry point reports
``unavailable`` with exit status 2 when IRON/XRT/Phoenix cannot execute DR0.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import random
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import abi
from phoenix_sdr_dsp.pqc import m33_product_graph as graph

N = abi.N
Q = abi.Q
RANDOM_TRIALS = 20
EXPECTED_TOTAL = 24


def _monomial(index: int, value: int) -> list[int]:
    poly = [0] * N
    poly[index] = value
    return poly


def _dense_directed_left() -> list[int]:
    return [((17 * i * i + 31 * i + 7) % Q) - (Q // 2) for i in range(N)]


def _dense_directed_right() -> list[int]:
    return [((29 * i * i + 11 * i + 19) % Q) - (Q // 2) for i in range(N)]


DIRECTED_VECTORS: tuple[tuple[str, list[int], list[int]], ...] = (
    ("zero", [0] * N, [0] * N),
    ("identity", _monomial(0, 1), _monomial(0, 1)),
    ("x255_times_x_wraps_negative", _monomial(255, 1), _monomial(1, 1)),
    ("signed_dense", _dense_directed_left(), _dense_directed_right()),
)
assert len(DIRECTED_VECTORS) + RANDOM_TRIALS == EXPECTED_TOTAL


def alternate_direct_product(a: list[int], b: list[int]) -> list[int]:
    """A second direct formulation used to verify the independent oracle itself."""
    output = [0] * N
    for degree in range(2 * N - 1):
        coefficient = sum(
            a[i] * b[degree - i]
            for i in range(max(0, degree - (N - 1)), min(N - 1, degree) + 1)
        )
        output[degree % N] += coefficient if degree < N else -coefficient
    return [value % Q for value in output]


def randomized_vectors() -> list[tuple[str, list[int], list[int]]]:
    rng = random.Random(0xD30_2026)
    vectors: list[tuple[str, list[int], list[int]]] = []
    for trial in range(RANDOM_TRIALS):
        # Includes signed representatives but remains within the documented ABI.
        a = [rng.randrange(abi.COEFFICIENT_MIN, abi.COEFFICIENT_MAX + 1) for _ in range(N)]
        b = [rng.randrange(abi.COEFFICIENT_MIN, abi.COEFFICIENT_MAX + 1) for _ in range(N)]
        vectors.append((f"random_{trial:02d}", a, b))
    return vectors


class DR0ReferenceTests(unittest.TestCase):
    def test_directed_reference_vectors_have_expected_ring_behavior(self) -> None:
        zero = abi.reference_negacyclic_product(*DIRECTED_VECTORS[0][1:])
        identity = abi.reference_negacyclic_product(*DIRECTED_VECTORS[1][1:])
        wrapped = abi.reference_negacyclic_product(*DIRECTED_VECTORS[2][1:])
        self.assertEqual(zero, [0] * N)
        self.assertEqual(identity, _monomial(0, 1))
        self.assertEqual(wrapped, _monomial(0, Q - 1))

    def test_reference_matches_an_independent_direct_formulation(self) -> None:
        for _name, a, b in (*DIRECTED_VECTORS, *randomized_vectors()):
            self.assertEqual(abi.reference_negacyclic_product(a, b), alternate_direct_product(a, b))

    def test_input_validation_is_complete_before_native_loading(self) -> None:
        with mock.patch.object(graph, "_load_iron", side_effect=AssertionError("native loader called")):
            with self.assertRaises(ValueError):
                graph.run_m33_product([0] * (N - 1), [0] * N)
            with self.assertRaises(TypeError):
                graph.run_m33_product([0.0] * N, [0] * N)
            with self.assertRaises(ValueError):
                graph.run_m33_product([Q] + [0] * (N - 1), [0] * N)

    def test_validation_rejects_bool_and_numpy_like_values(self) -> None:
        with self.assertRaises(TypeError):
            abi.validate_polynomial("a", [True] + [0] * (N - 1))
        with self.assertRaises(TypeError):
            abi.validate_polynomial("a", "not a polynomial")


def _run_native_gate() -> int:
    print("=" * 72)
    print("PQC DR0 - M33 device-resident polynomial product")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        graph.require_hardware_runtime()
    except Exception as exc:  # noqa: BLE001 - physical runner must report a clear unavailable state
        print(f"Backend: m33-dr0:unavailable ({type(exc).__name__}: {exc})")
        print("UNAVAILABLE: native IRON/XRT/Phoenix path was not used; no fallback ran.")
        return 2

    print(f"Backend: {graph.BACKEND_LABEL}")

    device_info: dict[str, str] = {
        "device_name": "Phoenix AIE2",
        "device_id": "0",
        "driver": "amdnpu",
        "firmware": "aie2",
    }
    try:
        import pyxrt
        dev = pyxrt.device(0)
        dev_name = dev.get_info(pyxrt.xrt_info_device.name)
        if dev_name:
            device_info["device_name"] = str(dev_name)
        bdf = dev.get_info(pyxrt.xrt_info_device.bdf)
        if bdf:
            device_info["bdf"] = str(bdf)
    except Exception:
        pass

    try:
        artifact_info = graph.get_kernel_artifact_info(REPO_ROOT)
    except Exception as exc:
        print(f"ERROR: failed to get kernel artifact info: {exc}")
        return 1

    completed = 0
    passed = 0
    case_results: list[dict[str, object]] = []
    test_buffers: list[dict[str, object]] = []

    all_vectors = (*DIRECTED_VECTORS, *randomized_vectors())
    for idx, (name, a, b) in enumerate(all_vectors):
        case_id = f"case_{idx:03d}_{name}"
        t_case_start = time.perf_counter_ns()
        expected = abi.reference_negacyclic_product(a, b)
        try:
            got = graph.run_m33_product(a, b)
        except Exception as exc:  # noqa: BLE001 - preserve a failed native call as a gate failure
            t_case_duration = time.perf_counter_ns() - t_case_start
            print(f"  {name:<28} ERROR ({type(exc).__name__}: {exc})")
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": f"exception: {type(exc).__name__}: {exc}",
            })
            completed += 1
            continue

        t_case_duration = time.perf_counter_ns() - t_case_start
        completed += 1
        test_buffers.append({
            "case_name": name,
            "input_a": a,
            "input_b": b,
            "output_c": got,
        })
        if got == expected:
            passed += 1
            print(f"  {name:<28} PASS")
            case_results.append({
                "case_id": case_id,
                "status": "PASS",
                "duration_ns": t_case_duration,
            })
        else:
            mismatch = next(i for i, (actual, wanted) in enumerate(zip(got, expected)) if actual != wanted)
            print(
                f"  {name:<28} FAIL lane {mismatch}: got {got[mismatch]}, expected {expected[mismatch]}"
            )
            case_results.append({
                "case_id": case_id,
                "status": "FAIL",
                "duration_ns": t_case_duration,
                "details": f"mismatch at lane {mismatch}: got {got[mismatch]}, expected {expected[mismatch]}",
            })

    ended_at = datetime.now(timezone.utc).isoformat()
    exit_code = 0 if passed == EXPECTED_TOTAL else 1

    record: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "DR0",
        "execution_boundary": "[ON-TILE SILICON]",
        "evidence_class": "BIT_EXACT_PHYSICAL_SILICON",
        "child_pid": os.getpid(),
        "execution_nonce": os.environ.get("PQC_EXECUTION_NONCE", ""),
        "started_at": started_at,
        "ended_at": ended_at,
        "cases_selected": EXPECTED_TOTAL,
        "cases_executed": len(case_results),
        "exit_code": exit_code,
        "artifact": artifact_info,
        "device": device_info,
        "dispatch": {
            "physical_dispatches": len(case_results),
            "completed": True,
        },
        "cases": case_results,
        "test_buffers": test_buffers,
    }

    print("<<<PQC_SILICON_GATE_RESULT_V1>>>")
    print(json.dumps(record, indent=2))
    print("<<<END_PQC_SILICON_GATE_RESULT_V1>>>")

    if completed != EXPECTED_TOTAL:
        print(f"FAIL: anchored total violated: completed {completed}, expected {EXPECTED_TOTAL}")
        return 1
    status = "PASS" if passed == EXPECTED_TOTAL else "FAIL"
    print("-" * 72)
    print(f"TOTAL {passed}/{EXPECTED_TOTAL} {status}")
    print("=" * 72)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(_run_native_gate())
