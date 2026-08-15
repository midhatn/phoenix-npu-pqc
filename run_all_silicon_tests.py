# Purpose: Master Silicon Regression Test Suite for all SDR and Finite-Field DSP Milestones.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (4-Column Array).
# Verification: End-to-end automated execution and reporting of Milestones 3, 5, 6, 7, 8, 9, 9b,
#               10, 11, 12, 13, 14, 15, 15b, 17, 17p.
#
# History:
# - v0.2.0: Initial 12-milestone suite (M3, M5–M15).
# - v0.3.0: Extended to 16 milestones after tests/RENUMBERING.md alignment
#           (v0.2.1). Adds M9b (parallel pipeline), M15b (negacyclic polymul),
#           M17 (direct-DFT NPU FFT), M17p (4-column parallel NPU FFT). The four
#           additions had been silicon-validated independently and now run under
#           the same regression harness.
# - v0.4.0: M17 runner entry switched from tests/m17_fft_dft (O(N^2) DFT)
#           to tests/m17_radix2_fft/test_fft_m17_v3.py (radix-4 Stockham +
#           IFFT round-trip). Direct-DFT kernel left on disk, unhooked.
# - v0.4.0+install: Re-exec under third_party/mlir-aie/ironenv so a new user
#           can run `python run_all_silicon_tests.py` after `python install.py`
#           with no separate activate step.

import os
import subprocess
import sys
import time
from pathlib import Path

# Repo root auto-detected from this file's location:
#   run_all_silicon_tests.py lives at the repo root.
REPO_ROOT = Path(__file__).resolve().parent
TESTS_DIR = REPO_ROOT / "tests"
IRONENV_PYTHON = (
    REPO_ROOT / "third_party" / "mlir-aie" / "ironenv" / "Scripts" / "python.exe"
)
PEANO_DIR = (
    REPO_ROOT
    / "third_party"
    / "mlir-aie"
    / "ironenv"
    / "Lib"
    / "site-packages"
    / "llvm-aie"
)


def ensure_ironenv_interpreter():
    """Re-exec under checkout-local ironenv so `py run_all_silicon_tests.py`
    works after `py install.py` with no separate activate step.

    `py` on Windows is the [Python launcher](https://docs.python.org/3/using/windows.html#python-launcher-for-windows)
    and binds to the system CPython, which has no numpy / mlir_aie / pyxrt.
    iron_setup.py installs those into third_party/mlir-aie/ironenv:
      https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
    """
    if sys.platform != "win32":
        return
    if not IRONENV_PYTHON.is_file():
        print("ironenv not found at:")
        print(f"  {IRONENV_PYTHON}")
        print("A new clone needs the installer first:")
        print("  python install.py")
        sys.exit(2)
    wanted = IRONENV_PYTHON.resolve()
    current = Path(sys.executable).resolve()
    try:
        same = current.samefile(wanted)
    except OSError:
        same = current == wanted
    if not same:
        os.execv(str(wanted), [str(wanted), *sys.argv])
    # Pin PEANO to this checkout. install.py also setx's the user env, but
    # setx does not update the current process, and a later D: install would
    # otherwise steal C:'s user-level PEANO_INSTALL_DIR.
    #   https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setx
    if PEANO_DIR.is_dir():
        os.environ["PEANO_INSTALL_DIR"] = str(PEANO_DIR)


def run_test(name, path, script):
    print("\n=======================================================")
    print(f" Running: {name}")
    print(f" Directory: {path}")
    print("=======================================================")

    start_t = time.perf_counter()
    p = subprocess.run(
        [sys.executable, script],
        check=False,
        cwd=str(path),
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - start_t

    output = p.stdout.strip()
    errors = p.stderr.strip()

    print(output)
    if errors:
        print(f"\n[STDERR]:\n{errors}")

    passed = (p.returncode == 0) and ("PASS!" in output)
    status_str = "PASSED" if passed else "FAILED"
    print(f"--> Result: [{status_str}] in {elapsed:.2f}s")
    return passed, elapsed, output


def main():
    ensure_ironenv_interpreter()
    print("======================================================================")
    print("       PHOENIX SDR-DSP MASTER SILICON REGRESSION TEST SUITE           ")
    print("   Target: AMD Ryzen 9 7940HS Phoenix NPU1 (XDNA1 / AIE2 / Win11)     ")
    print("======================================================================")
    print(f" Interpreter: {sys.executable}")
    print(f" PEANO_INSTALL_DIR: {os.environ.get('PEANO_INSTALL_DIR', '(unset)')}")

    test_matrix = [
        (
            "Milestone 3: Single-Core SAXPY Vector Operation",
            TESTS_DIR / "m3_saxpy",
            "test_saxpy_m3.py",
        ),
        (
            "Milestone 5: 8-Tap Vectorized Low-Pass FIR Filter",
            TESTS_DIR / "m5_fir",
            "test_fir_m5.py",
        ),
        (
            "Milestone 6: Complex Mixer / NCO Frequency Downconverter",
            TESTS_DIR / "m6_mixer",
            "test_mixer_m6.py",
        ),
        (
            "Milestone 7: Vectorized Power / RSSI Energy Detector",
            TESTS_DIR / "m7_power",
            "test_power_m7.py",
        ),
        (
            "Milestone 8: Streaming Multi-Stage Fused Demodulator Pipeline",
            TESTS_DIR / "m8_pipeline",
            "test_pipeline_m8.py",
        ),
        (
            "Milestone 9: 4-Column Parallel FIR Filter (Hardware Scaling)",
            TESTS_DIR / "m9_parallel",
            "test_parallel_m9.py",
        ),
        (
            "Milestone 9b: 4-Column Parallel Multi-Stage Demodulator Pipeline",
            TESTS_DIR / "m9b_parallel_pipeline",
            "test_parallel_pipeline_m10.py",
        ),
        (
            "Milestone 10: Modular Arithmetic & Barrett Reduction (mod 3329)",
            TESTS_DIR / "m10_modular",
            "test_modular_m10.py",
        ),
        (
            "Milestone 11: Radix-2 NTT Butterfly Kernel (mod 3329)",
            TESTS_DIR / "m11_butterfly",
            "test_butterfly_m11.py",
        ),
        (
            "Milestone 12: CPU NTT/INTT Reference & Constant Generator",
            TESTS_DIR / "m12_ntt_ref",
            "test_ntt_reference_m12.py",
        ),
        (
            "Milestone 13: 16-Point Vectorized NPU NTT (64 Batches)",
            TESTS_DIR / "m13_ntt16",
            "test_ntt16_m13.py",
        ),
        (
            "Milestone 14: 256-Point Vectorized NPU NTT (4 Batches)",
            TESTS_DIR / "m14_ntt256",
            "test_ntt256_m14.py",
        ),
        (
            "Milestone 15: NPU INTT & Cyclic Polynomial Multiplication",
            TESTS_DIR / "m15_polymul",
            "test_polymul_m15.py",
        ),
        (
            "Milestone 15b: NPU Negacyclic Polynomial Multiplication (Kyber ring)",
            TESTS_DIR / "m15b_negacyclic",
            "test_negacyclic_m16.py",
        ),
        (
            "Milestone 17: 64-Point Radix-4 Stockham FFT + IFFT (NPU1)",
            TESTS_DIR / "m17_radix2_fft",
            "test_fft_m17_v3.py",
        ),
        (
            "Milestone 17p: 4-Column Parallel 64-Point FFT Channelizer",
            TESTS_DIR / "m17p_fft_parallel",
            "test_parallel_fft_m12.py",
        ),
    ]

    results = []
    total_start = time.perf_counter()

    for name, path, script in test_matrix:
        passed, elapsed, _ = run_test(name, path, script)
        results.append((name, passed, elapsed))

    total_elapsed = time.perf_counter() - total_start

    print("\n\n======================================================================")
    print("                     REGRESSION EXECUTION SUMMARY                     ")
    print("======================================================================")
    all_passed = True
    for name, passed, elapsed in results:
        status_tag = "[ PASS ]" if passed else "[ FAIL ]"
        if not passed:
            all_passed = False
        print(f" {status_tag} {name:<70} ({elapsed:.2f}s)")

    print("----------------------------------------------------------------------")
    print(
        f" Total Tests Run: {len(results)} | Passed: {sum(1 for _, p, _ in results if p)} | Failed: {sum(1 for _, p, _ in results if not p)}"
    )
    print(f" Total Elapsed Time: {total_elapsed:.2f} seconds")

    if all_passed:
        print(
            "\n *** ALL SILICON DSP & NTT REGRESSION TESTS PASSED BIT-ACCURATELY! ***\n"
        )
    else:
        print("\n *** SOME REGRESSION TESTS FAILED. PLEASE REVIEW LOGS. ***\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
