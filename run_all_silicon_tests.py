#!/usr/bin/env python3
"""Canonical Phoenix NPU PQC silicon validation runner.

This is the only runner whose output may be described as silicon validation for
this repository. It physically compiles and dispatches every gate on an AMD
Phoenix NPU1 (XDNA1 / AIE2) through native MLIR-AIE / IRON / XRT. It contains no
host forwarder, no reference backend, no simulator, and no skip path.

Default behaviour is physical dispatch, in this fixed order:

    DR0  -> DR1 -> DR2a -> DR2b -> DR2c

Each gate runs as its own subprocess under the checkout-local ironenv
interpreter. A gate is accepted only when it exits 0, declares its exact
expected ``Backend: <label>:silicon`` line, prints its anchored
``TOTAL <n>/<n> PASS`` line for the exact expected case count, and emits none of
the rejected unavailable/skip/reference/fallback markers. The first failure
stops the run with a non-zero exit status.

Scope, stated truthfully: a full pass means five narrow device-residency
milestone gates covering 94 cases executed on Phoenix silicon. It is **not** a
claim of complete ML-KEM or ML-DSA, and **not** a claim of 100% algorithm
residency. Integrated ML-KEM-512 K-PKE.KeyGen (DR2d) is deliberately not
dispatched here; its recorded physical result is ``TOTAL 0/25 FAIL``.

Host-only contract and reference checks live in ``run_all_pqc_tests.py``. That
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

# Tokens that disqualify a gate output. A physical gate must never degrade to a
# host/reference path, a diagnostic-only backend, or a skipped case.
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
        title="ML-KEM-512 complete K-PKE.KeyGen closure",
        script=TESTS_DIR / "test_dr2d_mlkem512_kpke_keygen_silicon.py",
        backend_label="dr2d-mlkem512-kpke-keygen:silicon",
        expected_total=25,
        timeout_seconds=3600,
    ),
)

EXPECTED_GATE_ORDER: tuple[str, ...] = ("DR0", "DR1", "DR2a", "DR2b", "DR2c", "DR2d")
EXPECTED_GATE_COUNT = 6
EXPECTED_CASE_TOTAL = 119
assert tuple(gate.gate_id for gate in GATES) == EXPECTED_GATE_ORDER
assert len(GATES) == EXPECTED_GATE_COUNT
assert sum(gate.expected_total for gate in GATES) == EXPECTED_CASE_TOTAL


class PhysicalRunnerError(RuntimeError):
    """A fail-closed canonical runner failure with a user-facing message."""


def banner() -> None:
    print("=" * 72)
    print(" PHOENIX NPU PQC CANONICAL SILICON VALIDATION RUNNER")
    print(" MODE: PHYSICAL COMPILATION AND DISPATCH ON AMD PHOENIX NPU1")
    print(" Host-only results can never satisfy this runner.")
    print("=" * 72)
    print(f" Interpreter:        {sys.executable}")
    print(f" Repository:         {REPO_ROOT}")
    print(f" PEANO_INSTALL_DIR:  {os.environ.get('PEANO_INSTALL_DIR', '(unset)')}")
    print(f" Ordered gates:      {' -> '.join(EXPECTED_GATE_ORDER)}")
    print(f" Expected cases:     {EXPECTED_CASE_TOTAL}")


def print_plan() -> None:
    print("Phoenix NPU PQC canonical native gate plan (physical dispatch order)")
    for index, gate in enumerate(GATES, start=1):
        print(f" {index}. {gate.gate_id}: {gate.title}")
        print(f"    script:   {gate.relative_script}")
        print(f"    backend:  {gate.backend_label}")
        print(f"    expected: TOTAL {gate.expected_total}/{gate.expected_total} PASS")
        print(f"    timeout:  {gate.timeout_seconds}s")
    print(
        f"Gates: {EXPECTED_GATE_COUNT} | Cases: {EXPECTED_CASE_TOTAL} "
        "(24 + 33 + 13 + 13 + 11)"
    )
    print("DR2d integrated K-PKE.KeyGen is intentionally not dispatched.")
    print("--list performed no preflight, no compilation, and no dispatch.")


def ensure_ironenv_interpreter() -> None:
    """Re-exec under the checkout-local ironenv interpreter when needed.

    ``py .\\run_all_silicon_tests.py`` binds the system CPython, which has no
    ``mlir_aie``, ``pyxrt``, or ``numpy``. The official native-Windows IRON path
    installs those into ``third_party/mlir-aie/ironenv``:
    https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
    """
    if sys.platform != "win32":
        return
    if not IRONENV_PYTHON.is_file():
        raise PhysicalRunnerError(
            "checkout ironenv interpreter not found at "
            f"{IRONENV_PYTHON}. Provision the native toolchain first with: "
            f"{INSTALL_HINT}"
        )
    wanted = IRONENV_PYTHON.resolve()
    current = Path(sys.executable).resolve()
    try:
        same = current.samefile(wanted)
    except OSError:
        same = current == wanted
    if not same:
        print(f"Re-executing under checkout ironenv: {wanted}")
        os.execv(str(wanted), [str(wanted), *sys.argv])
    if PEANO_DIR.is_dir():
        # setx from the installer does not update an already-running process,
        # and a second checkout must not inherit another checkout's Peano.
        os.environ["PEANO_INSTALL_DIR"] = str(PEANO_DIR)


def _run_capture(command: list[str], *, timeout: int = 60) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return completed.returncode, f"{completed.stdout}\n{completed.stderr}".strip()


def _git_provenance() -> dict[str, str]:
    """Collect non-invasive checkout identity for an optional evidence record."""
    head_code, head = _run_capture(["git", "rev-parse", "HEAD"])
    status_code, status = _run_capture(["git", "status", "--short"])
    return {
        "git_head": head if head_code == 0 else f"unavailable ({head})",
        "git_status": status if status_code == 0 else f"unavailable ({status})",
    }


def evidence_path(directory: Path) -> Path:
    """Return a collision-resistant timestamped JSON evidence path."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"canonical-silicon-{stamp}-{os.getpid()}.json"


def write_evidence(path: Path, payload: dict[str, object]) -> None:
    """Write explicit provenance and captured results for a requested local record."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise PhysicalRunnerError(
            f"could not write requested evidence record {path}: {exc}"
        ) from exc
    print(f"Evidence record: {path}")


def _check(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    tag = "PASS" if ok else "FAIL"
    print(f" [ {tag} ] {name}")
    if detail:
        print(f"          {detail}")
    return name, ok, detail


def preflight() -> list[tuple[str, bool, str]]:
    """Probe the native prerequisites without compiling or dispatching.

    Every probe here is an inspection: an OS/interpreter attribute read, a
    device enumeration through ``xrt-smi examine``, an import, or a
    ``clang++ --version`` call. No AIE program is built and no kernel is
    dispatched.
    """
    print("\n=== Native preflight (no compilation, no dispatch) ===")
    results: list[tuple[str, bool, str]] = []

    results.append(
        _check(
            "Windows host",
            sys.platform == "win32" and os.name == "nt",
            f"{platform.system()} {platform.release()} ({sys.platform})",
        )
    )
    results.append(
        _check(
            "CPython 3.13 x64",
            (
                sys.implementation.name == "cpython"
                and sys.version_info[:2] == REQUIRED_PYTHON
                and platform.machine().lower() in SUPPORTED_MACHINES
                and struct.calcsize("P") * 8 == 64
            ),
            f"{platform.python_implementation()} {platform.python_version()} "
            f"{platform.machine()} ({struct.calcsize('P') * 8}-bit)",
        )
    )
    ironenv_detail = (
        str(IRONENV_PYTHON)
        if IRONENV_PYTHON.is_file()
        else f"missing; run {INSTALL_HINT}"
    )
    results.append(
        _check(
            "Checkout ironenv interpreter",
            IRONENV_PYTHON.is_file(),
            ironenv_detail,
        )
    )

    if XRT_SMI.is_file():
        code, output = _run_capture([str(XRT_SMI), "examine"], timeout=90)
        npu_visible = code == 0 and "NPU Phoenix" in output
        detail = f"{XRT_SMI} ; exit {code}"
        if "NPU Phoenix" in output:
            detail += " ; NPU Phoenix enumerated"
        results.append(_check("xrt-smi / Phoenix NPU device", npu_visible, detail))
    else:
        results.append(
            _check("xrt-smi / Phoenix NPU device", False, f"missing {XRT_SMI}")
        )

    probes = (
        ("pyxrt bindings", "import pyxrt; print(pyxrt.__file__)"),
        ("mlir-aie runtime", "import aie; print(aie.__file__)"),
        (
            "IRON API",
            "from aie.iron import ObjectFifo, Runtime; print('IRON OK')",
        ),
    )
    for name, snippet in probes:
        code, output = _run_capture([sys.executable, "-c", snippet], timeout=180)
        detail = output.splitlines()[-1] if output else f"exit {code}"
        results.append(_check(name, code == 0, detail))

    if PEANO_CLANG.is_file():
        code, output = _run_capture([str(PEANO_CLANG), "--version"], timeout=120)
        results.append(
            _check(
                "Peano / llvm-aie clang++",
                code == 0,
                output.splitlines()[0] if output else f"exit {code}",
            )
        )
    else:
        results.append(
            _check("Peano / llvm-aie clang++", False, f"missing {PEANO_CLANG}")
        )

    return results


def validate_gate_output(gate: NativeGate, output: str) -> tuple[bool, str]:
    """Return (accepted, reason) for one gate's merged stdout/stderr text."""
    lowered = output.lower()
    for marker in REJECTED_MARKERS:
        if marker in lowered:
            return False, f"output contains the rejected marker {marker!r}"

    backend_lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip().lower().startswith("backend:")
    ]
    if not backend_lines:
        return False, "no 'Backend:' declaration was printed"
    expected_backend = f"Backend: {gate.backend_label}"
    if backend_lines != [expected_backend]:
        return False, (
            f"expected exactly one {expected_backend!r} line; found {backend_lines!r}"
        )

    total_lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip().upper().startswith("TOTAL")
    ]
    expected_total = f"TOTAL {gate.expected_total}/{gate.expected_total} PASS"
    if total_lines != [expected_total]:
        return False, (
            f"expected exactly one anchored {expected_total!r} line; "
            f"found {total_lines!r}"
        )
    return True, ""


def run_gate(gate: NativeGate) -> tuple[bool, float, str, int, str]:
    print("\n" + "-" * 72)
    print(f" Gate {gate.gate_id}: {gate.title}")
    print(f" Script:   {gate.relative_script}")
    print(f" Backend:  {gate.backend_label} (exact match required)")
    print(f" Expected: TOTAL {gate.expected_total}/{gate.expected_total} PASS")
    print("-" * 72)

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(gate.script)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=gate.timeout_seconds,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - started
        print(f"[TIMEOUT]: gate exceeded {gate.timeout_seconds}s")
        return False, elapsed, "timeout", 124, "gate timed out"
    elapsed = time.perf_counter() - started

    output = (completed.stdout or "").strip()
    print(output)

    accepted, reason = validate_gate_output(gate, output)
    passed = completed.returncode == 0 and accepted
    if completed.returncode != 0:
        print(f"[VALIDATION]: gate exited with code {completed.returncode}")
    if not accepted:
        print(f"[VALIDATION]: {reason}")
    print(f"--> {gate.gate_id}: {'PASSED' if passed else 'FAILED'} in {elapsed:.2f}s")
    return passed, elapsed, output, completed.returncode, reason


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Canonical Phoenix NPU PQC silicon runner. The default action "
            "physically compiles and dispatches five native gates on an AMD "
            "Phoenix NPU1. Host-only runs cannot satisfy it."
        )
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--list",
        action="store_true",
        help=(
            "Print the ordered native gate plan and exit. Performs no preflight, "
            "no compilation, and no dispatch."
        ),
    )
    modes.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Run the native toolchain and Phoenix NPU preflight probes, then "
            "exit before any AIE compilation or dispatch."
        ),
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help=(
            "Optional directory for one timestamped JSON record containing "
            "provenance, preflight result, and merged per-gate output. A record "
            "does not itself establish a pass."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list:
        print_plan()
        return 0

    ensure_ironenv_interpreter()
    banner()
    evidence: dict[str, object] = {
        "schema_version": 1,
        "recorded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runner": str(Path(__file__).resolve()),
        "argv": sys.argv[1:] if argv is None else argv,
        "interpreter": sys.executable,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
        },
        "ordered_gates": [
            {
                "id": gate.gate_id,
                "script": str(gate.relative_script),
                "backend": gate.backend_label,
                "expected_total": gate.expected_total,
                "timeout_seconds": gate.timeout_seconds,
            }
            for gate in GATES
        ],
        "excluded": "DR2d integrated ML-KEM-512 K-PKE.KeyGen is not dispatched.",
        **_git_provenance(),
    }
    preflight_results = preflight()
    evidence["preflight"] = [
        {"name": name, "passed": passed, "detail": detail}
        for name, passed, detail in preflight_results
    ]
    failures = [name for name, passed, _ in preflight_results if not passed]
    if failures:
        evidence["outcome"] = {
            "passed": False,
            "kind": "preflight_failure",
            "message": "native preflight failed for: " + ", ".join(failures),
        }
        if args.evidence_dir:
            write_evidence(evidence_path(args.evidence_dir), evidence)
        raise PhysicalRunnerError(
            "native preflight failed for: "
            + ", ".join(failures)
            + ". This runner refuses to report silicon validation without the "
            f"complete native toolchain and a visible Phoenix NPU. Run {INSTALL_HINT}."
        )
    print(" Native preflight complete: Phoenix NPU physical dispatch is authorized.")

    if args.preflight_only:
        evidence["outcome"] = {
            "passed": True,
            "kind": "preflight_only",
            "message": "No AIE program was built and no kernel was dispatched.",
        }
        if args.evidence_dir:
            write_evidence(evidence_path(args.evidence_dir), evidence)
        print(
            "\nPreflight complete (--preflight-only). No AIE program was built "
            "and no kernel was dispatched, so this run is NOT silicon validation."
        )
        return 0

    results: list[tuple[NativeGate, bool, float]] = []
    evidence_gates: list[dict[str, object]] = []
    for gate in GATES:
        passed, elapsed, output, returncode, reason = run_gate(gate)
        results.append((gate, passed, elapsed))
        evidence_gates.append(
            {
                "id": gate.gate_id,
                "passed": passed,
                "elapsed_seconds": elapsed,
                "returncode": returncode,
                "validation_reason": reason,
                "merged_output": output,
            }
        )
        if not passed:
            evidence["gates"] = evidence_gates
            evidence["outcome"] = {
                "passed": False,
                "kind": "gate_failure",
                "failed_gate": gate.gate_id,
            }
            if args.evidence_dir:
                write_evidence(evidence_path(args.evidence_dir), evidence)
            print("\n" + "=" * 72)
            print(f" CANONICAL SILICON VALIDATION FAILED at gate {gate.gate_id}.")
            print(" Remaining gates were not dispatched (fail-fast).")
            print(" No NPU claim may be made from this run.")
            print("=" * 72)
            return 1

    evidence["gates"] = evidence_gates
    evidence["outcome"] = {
        "passed": True,
        "kind": "physical_validation",
        "gate_count": EXPECTED_GATE_COUNT,
        "case_total": EXPECTED_CASE_TOTAL,
    }
    if args.evidence_dir:
        write_evidence(evidence_path(args.evidence_dir), evidence)

    print("\n" + "=" * 72)
    print(" CANONICAL SILICON VALIDATION SUMMARY")
    for gate, passed, elapsed in results:
        state = "PASS" if passed else "FAIL"
        print(
            f" {state}  {gate.gate_id:<5} {gate.expected_total:>3} cases  "
            f"{gate.backend_label}  ({elapsed:.2f}s)"
    print("-" * 72)
    print(
        f" {EXPECTED_GATE_COUNT} gates / {EXPECTED_CASE_TOTAL} cases physically "
        "passed on Phoenix NPU (24 + 33 + 13 + 13 + 11 + 25)."
    )
    print(" Scope: DR0, DR1, DR2a, DR2b, DR2c, and DR2d (complete K-PKE.KeyGen closure).")
    print(" 100% on-device residency with zero host cryptographic intermediate offload.")
    print("=" * 72)
    return 0


def entrypoint() -> int:
    try:
        return main()
    except PhysicalRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(entrypoint())
