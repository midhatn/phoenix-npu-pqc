# Purpose: Master Silicon Regression Test Suite for all SDR and Finite-Field DSP Milestones.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (4-Column Array).
# Verification: End-to-end automated execution and reporting of Milestones 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15.

import subprocess
import sys
import time
from pathlib import Path


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
    print("======================================================================")
    print("       PHOENIX SDR-DSP MASTER SILICON REGRESSION TEST SUITE           ")
    print("   Target: AMD Ryzen 9 7940HS Phoenix NPU1 (XDNA1 / AIE2 / Win11)     ")
    print("======================================================================")

    test_matrix = [
        (
            "Milestone 3: Single-Core SAXPY Vector Operation",
            Path(r"C:\phoenix-sdr-dsp\third_party\mlir-aie\programming_examples\getting_started\01_SAXPY"),
            "saxpy_m3.py"
        ),
        (
            "Milestone 5: 8-Tap Vectorized Low-Pass FIR Filter",
            Path(r"C:\phoenix-sdr-dsp\tests\m5_fir"),
            "test_fir_m5.py"
        ),
        (
            "Milestone 6: Complex Mixer / NCO Frequency Downconverter",
            Path(r"C:\phoenix-sdr-dsp\tests\m6_mixer"),
            "test_mixer_m6.py"
        ),
        (
            "Milestone 7: Vectorized Power / RSSI Energy Detector",
            Path(r"C:\phoenix-sdr-dsp\tests\m7_power"),
            "test_power_m7.py"
        ),
        (
            "Milestone 8: Streaming Multi-Stage Fused Demodulator Pipeline",
            Path(r"C:\phoenix-sdr-dsp\tests\m8_pipeline"),
            "test_pipeline_m8.py"
        ),
        (
            "Milestone 9: 4-Column Parallel FIR Filter (Hardware Scaling)",
            Path(r"C:\phoenix-sdr-dsp\tests\m9_parallel"),
            "test_parallel_m9.py"
        ),
        (
            "Milestone 10: Modular Arithmetic & Barrett Reduction (mod 3329)",
            Path(r"C:\phoenix-sdr-dsp\tests\m10_modular"),
            "test_modular_m10.py"
        ),
        (
            "Milestone 11: Radix-2 NTT Butterfly Kernel (mod 3329)",
            Path(r"C:\phoenix-sdr-dsp\tests\m11_butterfly"),
            "test_butterfly_m11.py"
        ),
        (
            "Milestone 12: CPU NTT/INTT Reference & Constant Generator",
            Path(r"C:\phoenix-sdr-dsp\tests\m12_ntt_ref"),
            "test_ntt_reference_m12.py"
        ),
        (
            "Milestone 13: 16-Point Vectorized NPU NTT (64 Batches)",
            Path(r"C:\phoenix-sdr-dsp\tests\m13_ntt16"),
            "test_ntt16_m13.py"
        ),
        (
            "Milestone 14: 256-Point Vectorized NPU NTT (4 Batches)",
            Path(r"C:\phoenix-sdr-dsp\tests\m14_ntt256"),
            "test_ntt256_m14.py"
        ),
        (
            "Milestone 15: NPU INTT & Cyclic Polynomial Multiplication",
            Path(r"C:\phoenix-sdr-dsp\tests\m15_polymul"),
            "test_polymul_m15.py"
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
        print(f" {status_tag} {name:<65} ({elapsed:.2f}s)")

    print("----------------------------------------------------------------------")
    print(f" Total Tests Run: {len(results)} | Passed: {sum(1 for _, p, _ in results if p)} | Failed: {sum(1 for _, p, _ in results if not p)}")
    print(f" Total Elapsed Time: {total_elapsed:.2f} seconds")
    
    if all_passed:
        print("\n *** ALL SILICON DSP & NTT REGRESSION TESTS PASSED BIT-ACCURATELY! ***\n")
    else:
        print("\n *** SOME REGRESSION TESTS FAILED. PLEASE REVIEW LOGS. ***\n")

if __name__ == "__main__":
    main()
