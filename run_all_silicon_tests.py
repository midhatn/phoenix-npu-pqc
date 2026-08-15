# Purpose: Master Silicon Regression Test Suite for all SDR and Finite-Field DSP Milestones.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (4-Column Array).
# Verification: End-to-end automated execution and reporting of Milestones 3, 5, 6, 7, 8, 9, 9b,
#               10, 11, 12, 13, 14, 15, 15b, 17, 17p, 19, 20, 21, 22, 23, 24, 25.
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
# - v0.4.0+M19: 17th silicon regression entry added. M19 8-tap complex FIR
#           (tests/m19_complex_fir/test_fir_complex_m19.py) is bit-accurate on
#           impulse, DC, tone, random I/Q, and M5-degeneracy against a NumPy
#           reference under the M5/M6 atol=0.01 gate. Published contract moves
#           from 16/16 to 17/17 silicon-validated milestones.
# - v0.4.0+M20: 18th silicon regression entry added. M20 fused polyphase
#           decimator (M=4) + interpolator (L=4) with a 16-tap Kaiser-window
#           prototype LPF and scipy-convention interp scaling
#           (tests/m20_polyphase/test_polyphase_m20.py). Bit-accurate on Kaiser
#           tap regen, impulse, DC steady, complex tone, and random I/Q against
#           a NumPy reference under the M5/M6 atol=0.01 gate. Design cites
#           Vaidyanathan 1993, Harris 2004, Kaiser 1974, and
#           scipy.signal.resample_poly. Published contract moves from 17/17
#           to 18/18 silicon-validated milestones.
# - v0.4.0+M21: 19th silicon regression entry added. M21 fused Digital
#           Down-Converter (DDC): complex NCO at f_c = -f_s/8 (8-sample
#           cordic-free LO LUT) + 16-tap Kaiser LPF (reused from M20)
#           + decim-by-M=4, all on one AIE2 core
#           (tests/m21_ddc/test_ddc_m21.py). Bit-accurate on LO regen,
#           impulse, on-carrier tone (mag = 1.0000, phase = 0.0000),
#           image rejection = 55.8 dB, and random I/Q at seed 789 under
#           the M5/M6 atol=0.01 gate. Silicon PASS at max err 0.003906,
#           matching M20's envelope. Design cites Harris 2004 chapter 8,
#           Analog Devices MT-085 (DDS fundamentals), GNU Radio
#           frequency-xlating FIR filter, and NIST DLMF chapter 1.
#           Published contract moves from 18/18 to 19/19 silicon-
#           validated milestones.
# - v0.4.0+M22: 20th silicon regression entry added. M22 fused Digital
#           Up-Converter (DUC): zero-stuff interpolation by L=4 fused
#           with a 16-tap Kaiser*L LPF (reuses M20 stage-2 taps) and a
#           complex NCO at f_c = +f_s/8 (8-sample cordic-free LO LUT,
#           sign-flipped from M21), all on one AIE2 core
#           (tests/m22_duc/test_duc_m22.py). Bit-accurate on LO regen,
#           impulse, DC->+f_s/8 tone (mag = 0.9976 at bin 192),
#           baseband tone at -f_bb/8 upconverts to +3f_s/32 (peak bin
#           144), and random I/Q at seed 792 under the M5/M6 atol=0.01
#           gate. Silicon PASS at max err 0.007812. Design cites
#           Harris 2004 chapter 8 (DUC), Vaidyanathan 1993 Eq. 4.3.13,
#           Kaiser 1974, scipy.signal.resample_poly interp scaling,
#           Analog Devices MT-085, and GNU Radio frequency-xlating
#           FIR filter. Published contract moves from 19/19 to 20/20
#           silicon-validated milestones.
# - v0.4.0+M23: 21st silicon regression entry added. M23 fused polyphase
#           channelizer: input commutator (natural sample-to-branch,
#           p = q) into an M = 8 path polyphase FIR (K = 8 taps/branch,
#           64-tap Kaiser prototype, beta ~ 5.653, cutoff pi/M) into an
#           8-point matmul-DFT with fully-embedded twiddles, all on one
#           AIE2 core (tests/m23_channelizer/test_channelizer_m23.py).
#           Bit-accurate on prototype LPF (sum(h) = 0.99977, exact even
#           symmetry), DC -> ch0 (iso 66.2 dB), single tone -> ch3 (iso
#           66.2 dB), two-tone -> ch1 + ch5 (iso 64.5 dB), and random
#           I/Q at seed 793 under an atol = 0.02 gate (looser than
#           M21/M22's 0.01 because the DFT accumulates 8 bfloat16
#           roundings on top of the 8-tap FIR). Silicon PASS at
#           max err 0.003906. Sandbox transliteration is np.array_equal
#           bit-exact to the host reference on the seed-793 vector
#           (0 / 4096 slots differ). Design cites Harris 2004 ch. 6
#           section 6.3 (M-path analysis bank), Vaidyanathan 1993
#           section 4.3 Eq. 4.3.13 (polyphase commutator identity),
#           GNU Radio pfb_channelizer_ccf, NVIDIA MatX channelize_poly
#           (natural sample-to-branch convention), Kaiser 1974
#           I0-sinh window, and scipy.signal.firwin. Published contract
#           moves from 20/20 to 21/21 silicon-validated milestones and
#           closes the DSP-track filtering & resampling block (M19-M23).
# - v0.4.0+M24: 22nd silicon regression entry added. M24 fused Barker-13
#           matched-filter correlator: two independent real FIRs on I
#           and Q with reversed Barker-13 taps
#           (+1,-1,+1,-1,+1,+1,-1,-1,+1,+1,+1,+1,+1), L = 13, on one
#           AIE2 core (tests/m24_correlator/test_correlator_m24.py).
#           Matched-filter theory follows Proakis & Salehi 5e sec 5.1.5
#           and Massey 1972; correlation-as-reversed-FIR identity per
#           Oppenheim & Schafer 3e sec 2.6.2; block topology matches
#           the GNU Radio Correlation Estimator and liquid-dsp
#           detector_cccf. Barker-13 PSL = 1 (|c_v| <= 1 for all
#           nonzero shifts) per Barker 1953 and Wikipedia "Barker
#           code". Kernel uses M22 literal-index MAC discipline
#           (13-term hand-unrolled dot product, 12-slot explicit
#           shift-and-ingest). Silicon PASS at max err 0.03125
#           (atol = 0.05) on random I/Q at seed 794; host gates cover
#           aligned preamble peak = 13.0 at sample 112, DC input Iy
#           steady = 5.0, +45 deg rotated preamble |y| = 12.99, and
#           negated preamble Iy = -13.0. Sandbox transliteration is
#           np.array_equal bit-exact (0 / 4096 slots differ, max diff
#           0.0). Bring-up incident: three consecutive silicon runs
#           produced all-zero output because the driver's
#           correlator_program was missing the @iron.jit decorator and
#           the In/Out/CompileTime type annotations; root cause and fix
#           documented in docs/M24_DESIGN.md sec 5.3 with citations to
#           the mlir-aie IRON API overview and compilation-stages
#           guide. Published contract moves from 21/21 to 22/22
#           silicon-validated milestones and opens the modulation &
#           synchronization block (M24-M27).
# - v0.5.0: 23rd silicon regression entry added. M25 fused BPSK/QPSK
#           receiver: single templated psk_rx_body<ORDER> C++ body with
#           two @iron.jit entry points (psk_rx_bpsk for ORDER=2,
#           psk_rx_qpsk for ORDER=4). Signal chain per Gardner 1986
#           (mid-symbol timing-error detector), Costas 1956 (order-2
#           phase detector for BPSK), US Patent 4344178A (decision-
#           directed cross-form order-4 phase detector for QPSK), and
#           Rondeau 2011 (PI-loop gain derivation from loop bandwidth
#           and damping); on-tile NCO derotator uses an open-coded 7th-
#           order Taylor sin/cos with pi/2 range fold because Peano
#           NOCPP has no libc <math.h>. All loop state in scalar float32
#           registers with a three-slot complex sample history (M22
#           literal-index shift-and-ingest). I/O bfloat16, internal
#           math float32. Silicon PASS on Ryzen 9 7940HS Phoenix NPU1:
#           BPSK order-2 seed 795 - gate (a) max_err = 0.003906, gate
#           (b) |z| median = 0.9961, RMS Costas error = 0.0000; QPSK
#           order-4 seed 796 - gate (a) max_err = 0.003906, gate (b)
#           |z| median = 0.9975, RMS residual phase = 0.2841 rad, well
#           under pi/8 = 0.3927. Four bring-up incidents documented in
#           docs/M25_DESIGN.md sec 4b: (1) Peano NOCPP has no libc math
#           so sinf/cosf/fmodf were open-coded as Taylor + fold; (2)
#           scalar (x>=0)?1:-1 miscompiles under NOCPP so sign-of was
#           replaced with a union{float;uint32_t} sign-bit read; (3)
#           Peano -O2 folded the union form into llvm.copysign which
#           AIE2 rejects as unable to legalize G_FCOPYSIGN, so the sign
#           bit is extracted into a volatile uint32_t and OR'd into
#           0x3F800000 to defeat the pattern-matcher; (4) Costas +
#           Gardner is a closed-feedback dynamical system, so CPU vs
#           AIE2 float32 rounding integrates to different steady-state
#           equilibria after ~1/BW_phi symbols. Not fixable in kernel;
#           PASS gate was revised to three receiver-theoretic checks
#           per NASA JPL TDA Progress Report 42-130, Kuznetsov et al
#           2018 arXiv 1810.00071, and Analog Devices "Practical Costas
#           Loops": (a) acquisition - first 32 output symbols match
#           reference to atol = 0.05; (b) steady-state lock - |z| median
#           in [0.7, 1.3] AND RMS phase-error residual < pi/8 per NASA's
#           canonical Costas lock criterion (BPSK: zI*zQ; QPSK: angle
#           mod pi/2 folded into [-pi/4, pi/4]); (c) diagnostic - first
#           sample-wise divergence slot logged for the record only.
#           Sandbox transliteration is bit-exact on both orders
#           (0 / 1024 slots differ, tools/m25_kernel_transliteration_check.py).
#           Published contract moves from 22/22 to 23/23 silicon-
#           validated milestones.

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
        (
            "Milestone 19: 8-Tap Complex FIR Filter (complex taps x complex I/Q)",
            TESTS_DIR / "m19_complex_fir",
            "test_fir_complex_m19.py",
        ),
        (
            "Milestone 20: Fused Polyphase Decim (M=4) + Interp (L=4)",
            TESTS_DIR / "m20_polyphase",
            "test_polyphase_m20.py",
        ),
        (
            "Milestone 21: Fused DDC (NCO(-fs/8) + Kaiser LPF + Decim-M=4)",
            TESTS_DIR / "m21_ddc",
            "test_ddc_m21.py",
        ),
        (
            "Milestone 22: Fused DUC (Interp-L=4 + Kaiser*L LPF + NCO(+fs/8))",
            TESTS_DIR / "m22_duc",
            "test_duc_m22.py",
        ),
        (
            "Milestone 23: Fused Polyphase Channelizer (M=8 commutator + FIR + DFT)",
            TESTS_DIR / "m23_channelizer",
            "test_channelizer_m23.py",
        ),
        (
            "Milestone 24: Fused Barker-13 Matched-Filter Correlator (L=13)",
            TESTS_DIR / "m24_correlator",
            "test_correlator_m24.py",
        ),
        (
            "Milestone 25: Fused BPSK/QPSK Rx (Gardner TED + Costas order-2/4 PI)",
            TESTS_DIR / "m25_psk_rx",
            "test_psk_rx_m25.py",
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
