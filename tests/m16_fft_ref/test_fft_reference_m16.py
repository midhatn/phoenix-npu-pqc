# Purpose: Master Prompt Milestone 16 — Independent CPU FFT/IFFT Reference.
# Target operating system: Windows 11 Pro 25H2.
# Target architecture: AMD Phoenix NPU1 / XDNA1 / AIE2 (CPU-side reference; no NPU dispatch).
# Transform Domain: Complex-valued discrete Fourier transform over C.
# Transform Lengths: N in {8, 16, 32, 64, 128, 256, 512, 1024} (power-of-2).
# Datatype: complex128 (double precision), matching NumPy's fft/ifft internally.
#
# This file serves the same role for the FFT/IFFT domain that
# `tests/m12_ntt_ref/test_ntt_reference_m12.py` serves for the NTT/INTT domain:
# it is a pure-Python, dependency-minimal, mathematically transparent reference
# that will act as the ground-truth oracle for the NPU FFT kernels (§16 M17)
# once they are implemented. It runs on the CPU only and has no MLIR-AIE or
# XRT dependencies, so it can execute in CI without silicon.
#
# ────────────────────────────────────────────────────────────────────────────
# References
# ────────────────────────────────────────────────────────────────────────────
#   [CT65]   Cooley, J. W. and Tukey, J. W. (1965). "An algorithm for the
#            machine calculation of complex Fourier series." Mathematics of
#            Computation 19(90): 297–301.
#            https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf
#
#   [Rice]   Rice University FFT tutorial (public, CC-BY):
#            https://repository.rice.edu/server/api/core/bitstreams/01e9e0a5-fa6f-453d-a1b5-8209fa0a565c/content
#
#   [McFee]  McFee, B. "Digital Signals Theory," §8.2 Fast Fourier Transform.
#            https://brianmcfee.net/dstbook-site/content/ch08-fft/FFT.html
#
#   [NumPy]  NumPy `numpy.fft.fft` documentation (used only for cross-check):
#            https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html
#
# ────────────────────────────────────────────────────────────────────────────
# Mathematical definitions
# ────────────────────────────────────────────────────────────────────────────
# For a length-N complex input vector x[0..N-1] the forward DFT is defined as
#
#       X[k] = sum_{n=0}^{N-1} x[n] * exp(-j*2*pi*k*n/N),   k = 0..N-1        (1)
#
# and the inverse DFT (IDFT) as
#
#       x[n] = (1/N) * sum_{k=0}^{N-1} X[k] * exp(+j*2*pi*k*n/N),  n = 0..N-1 (2)
#
# The direct evaluation of (1) is O(N^2). Cooley & Tukey [CT65] showed that
# when N is composite (in particular, N = 2^m) the sum can be recursively
# split into two half-length transforms of the even- and odd-indexed samples
# to obtain the radix-2 decimation-in-time (DIT) algorithm running in
# O(N log2 N) operations. The classical butterfly recurrence is
#
#       X[k]         = E[k] + w_N^k * O[k]
#       X[k + N/2]   = E[k] - w_N^k * O[k],   k = 0..N/2 - 1
#
# where E = DFT(x_even), O = DFT(x_odd), and w_N = exp(-j*2*pi/N) is the
# principal N-th root of unity ([CT65]; [Rice, §2]; [McFee, §8.2]).
#
# Numerical stability: the recursive radix-2 FFT accumulates O(log2 N)
# roundoff and its relative L2 error is bounded by a small multiple of
# log2(N) * eps, where eps is the machine epsilon of the arithmetic used
# (see Higham, "Accuracy and Stability of Numerical Algorithms," §24.1).
# For complex128 (eps ≈ 2.22e-16) and N ≤ 1024, the expected relative
# error against a direct DFT is on the order of 1e-13.

import cmath
import math
import numpy as np


# ============================================================================
# Reference implementations
# ============================================================================

def direct_dft(x):
    """
    Direct O(N^2) evaluation of eqn. (1). Serves as the mathematical
    ground truth: no algorithmic optimizations, no numerical tricks.
    Complexity: N^2 complex multiplications + N*(N-1) additions.

    Parameters
    ----------
    x : (N,) array_like of complex or real
        Input signal.

    Returns
    -------
    X : (N,) ndarray of complex128
        Forward DFT of x, per eqn. (1).
    """
    x = np.asarray(x, dtype=np.complex128)
    N = x.shape[0]
    n = np.arange(N)
    k = n.reshape(-1, 1)
    # Twiddle matrix W[k, n] = exp(-2*pi*j*k*n/N)
    W = np.exp(-2j * np.pi * k * n / N)
    return W @ x


def direct_idft(X):
    """
    Direct O(N^2) evaluation of eqn. (2). Ground truth for the inverse.

    Parameters
    ----------
    X : (N,) array_like of complex
        Frequency-domain input.

    Returns
    -------
    x : (N,) ndarray of complex128
        Inverse DFT of X, per eqn. (2).
    """
    X = np.asarray(X, dtype=np.complex128)
    N = X.shape[0]
    n = np.arange(N)
    k = n.reshape(-1, 1)
    W_inv = np.exp(+2j * np.pi * k * n / N)
    return (W_inv @ X) / N


def _is_power_of_two(N):
    return N > 0 and (N & (N - 1)) == 0


def radix2_fft_recursive(x):
    """
    Recursive radix-2 decimation-in-time Cooley-Tukey FFT [CT65]. Handles
    any power-of-2 length N. Complexity: (N/2) * log2(N) complex
    multiplications, N * log2(N) additions.

    This is the *reference algorithm*: written for mathematical clarity,
    not raw speed. It is the closest one-to-one Python transcription of
    the recurrence given in [CT65] eqn. (10)-(11).

    Parameters
    ----------
    x : (N,) array_like of complex or real
        Input signal. N MUST be a power of two.

    Returns
    -------
    X : (N,) ndarray of complex128
        Forward FFT of x, bit-exact to direct_dft(x) up to floating-point
        round-off (see numerical stability note above).

    Raises
    ------
    ValueError
        If N is not a positive power of 2.
    """
    x = np.asarray(x, dtype=np.complex128)
    N = x.shape[0]
    if not _is_power_of_two(N):
        raise ValueError(f"radix-2 FFT requires N to be a power of 2; got N={N}")

    if N == 1:
        return x.copy()

    even = radix2_fft_recursive(x[0::2])
    odd = radix2_fft_recursive(x[1::2])

    # Twiddle factors w_N^k = exp(-2*pi*j*k/N) for k = 0..N/2 - 1
    half = N // 2
    k = np.arange(half)
    twiddles = np.exp(-2j * np.pi * k / N)

    X = np.empty(N, dtype=np.complex128)
    X[:half] = even + twiddles * odd
    X[half:] = even - twiddles * odd
    return X


def _bit_reverse_indices(N):
    """Return the array of bit-reversed indices for length N = 2^m."""
    m = int(math.log2(N))
    idx = np.arange(N)
    result = np.zeros(N, dtype=np.int64)
    for i in range(N):
        rev = 0
        v = idx[i]
        for _ in range(m):
            rev = (rev << 1) | (v & 1)
            v >>= 1
        result[i] = rev
    return result


def radix2_fft_iterative(x):
    """
    Iterative in-place radix-2 DIT Cooley-Tukey FFT with bit-reversed
    input permutation. This variant maps directly onto the butterfly
    dataflow that the NPU M17 kernel will use ([CT65]; [Rice §2]),
    and thus serves as the closest CPU proxy for the NPU implementation.

    Parameters
    ----------
    x : (N,) array_like of complex or real
        Input signal. N MUST be a power of two.

    Returns
    -------
    X : (N,) ndarray of complex128
    """
    x = np.asarray(x, dtype=np.complex128)
    N = x.shape[0]
    if not _is_power_of_two(N):
        raise ValueError(f"radix-2 FFT requires N to be a power of 2; got N={N}")

    # Bit-reversal permutation
    rev = _bit_reverse_indices(N)
    X = x[rev].copy()

    # Butterflies over log2(N) stages
    stage_size = 2
    while stage_size <= N:
        half = stage_size // 2
        # Twiddles for this stage
        k = np.arange(half)
        twiddles = np.exp(-2j * np.pi * k / stage_size)
        for start in range(0, N, stage_size):
            # Copy top explicitly so the write to X[start:start+half] does
            # not invalidate the top-half reference before we compute the
            # bottom-half output.
            top = X[start : start + half].copy()
            bot = X[start + half : start + stage_size] * twiddles
            X[start : start + half] = top + bot
            X[start + half : start + stage_size] = top - bot
        stage_size <<= 1

    return X


def radix2_ifft_recursive(X):
    """
    Inverse FFT via the identity  IFFT(X) = conj(FFT(conj(X))) / N.
    Bit-exact to direct_idft up to double-precision round-off.
    """
    X = np.asarray(X, dtype=np.complex128)
    N = X.shape[0]
    return np.conj(radix2_fft_recursive(np.conj(X))) / N


# ============================================================================
# Regression tests
# ============================================================================

def _rel_err(a, b):
    """Relative L2 error ||a - b|| / ||b||."""
    b_norm = np.linalg.norm(b)
    if b_norm == 0.0:
        return np.linalg.norm(a - b)
    return np.linalg.norm(a - b) / b_norm


def _run_size(N, rng, verbose=True):
    """Run the full cross-check battery at length N. Returns True on all-pass."""
    if verbose:
        print(f"\n--- N = {N} ---")

    # Impulse: DFT of [1,0,0,...] must be [1,1,1,...]
    impulse = np.zeros(N, dtype=np.complex128)
    impulse[0] = 1.0
    dft_imp = direct_dft(impulse)
    rec_imp = radix2_fft_recursive(impulse)
    itr_imp = radix2_fft_iterative(impulse)
    expected_imp = np.ones(N, dtype=np.complex128)

    # Tolerance scaled to cover N up to 1024 (direct DFT accumulates O(N) round-off).
    tol_low_energy = 1e-11
    assert _rel_err(dft_imp, expected_imp) < tol_low_energy, "Impulse: direct DFT mismatch"
    assert _rel_err(rec_imp, expected_imp) < tol_low_energy, "Impulse: recursive FFT mismatch"
    assert _rel_err(itr_imp, expected_imp) < tol_low_energy, "Impulse: iterative FFT mismatch"
    if verbose:
        print("  [PASS] Impulse DFT/FFT (all three implementations)")

    # DC constant: DFT of [c,c,c,...] must be [c*N, 0, 0, ...]
    c = 3.14
    const_vec = np.full(N, c, dtype=np.complex128)
    dft_c = direct_dft(const_vec)
    rec_c = radix2_fft_recursive(const_vec)
    expected_c = np.zeros(N, dtype=np.complex128)
    expected_c[0] = c * N

    assert _rel_err(dft_c, expected_c) < tol_low_energy, "Constant: direct DFT mismatch"
    assert _rel_err(rec_c, expected_c) < tol_low_energy, "Constant: recursive FFT mismatch"
    if verbose:
        print("  [PASS] DC constant (energy concentrates at k=0)")

    # Pure tone at bin k0: DFT must be all-zero except X[k0] = N (and X[N-k0] for real inputs)
    if N >= 4:
        k0 = 1
        n_axis = np.arange(N)
        tone = np.exp(2j * np.pi * k0 * n_axis / N)  # complex exponential
        X_tone = radix2_fft_recursive(tone)
        expected_tone = np.zeros(N, dtype=np.complex128)
        expected_tone[k0] = N
        assert _rel_err(X_tone, expected_tone) < 1e-11, (
            f"Pure tone at k0={k0}: FFT does not concentrate energy correctly"
        )
        if verbose:
            print(f"  [PASS] Pure tone at k0={k0} → energy concentrated in X[{k0}]")

    # Random complex vector: all three FFT implementations must agree with direct DFT
    rand_re = rng.standard_normal(N)
    rand_im = rng.standard_normal(N)
    rand_vec = rand_re + 1j * rand_im

    dft_rand = direct_dft(rand_vec)
    rec_rand = radix2_fft_recursive(rand_vec)
    itr_rand = radix2_fft_iterative(rand_vec)
    np_rand = np.fft.fft(rand_vec)

    err_rec = _rel_err(rec_rand, dft_rand)
    err_itr = _rel_err(itr_rand, dft_rand)
    err_np = _rel_err(np_rand, dft_rand)
    tol = 1e-11  # generous tol for N up to 1024 in complex128

    assert err_rec < tol, f"Recursive FFT vs direct DFT: rel err {err_rec:.2e} exceeds {tol}"
    assert err_itr < tol, f"Iterative FFT vs direct DFT: rel err {err_itr:.2e} exceeds {tol}"
    assert err_np < tol, f"NumPy FFT vs direct DFT: rel err {err_np:.2e} exceeds {tol}"
    if verbose:
        print(f"  [PASS] Random complex vector cross-check")
        print(f"           recursive-vs-direct   rel err = {err_rec:.2e}")
        print(f"           iterative-vs-direct   rel err = {err_itr:.2e}")
        print(f"           numpy-vs-direct       rel err = {err_np:.2e}")

    # Round-trip: x == IFFT(FFT(x))
    X_rand = radix2_fft_recursive(rand_vec)
    x_back = radix2_ifft_recursive(X_rand)
    err_rt = _rel_err(x_back, rand_vec)
    assert err_rt < tol, f"Round-trip x == IFFT(FFT(x)): rel err {err_rt:.2e} exceeds {tol}"
    if verbose:
        print(f"  [PASS] Round-trip x == IFFT(FFT(x)), rel err = {err_rt:.2e}")

    # Parseval's / Plancherel's theorem: sum |x[n]|^2 == (1/N) * sum |X[k]|^2
    energy_time = float(np.sum(np.abs(rand_vec) ** 2))
    energy_freq = float(np.sum(np.abs(X_rand) ** 2)) / N
    parseval_err = abs(energy_time - energy_freq) / energy_time
    assert parseval_err < 1e-12, (
        f"Parseval energy conservation violated: rel err {parseval_err:.2e}"
    )
    if verbose:
        print(
            f"  [PASS] Parseval: sum|x[n]|^2 = {energy_time:.6f}, "
            f"(1/N)sum|X[k]|^2 = {energy_freq:.6f}, rel err = {parseval_err:.2e}"
        )

    return True


def main():
    print("=" * 74)
    print("  MILESTONE 16 — CPU FFT/IFFT REFERENCE")
    print("  Radix-2 Cooley-Tukey (recursive + iterative bit-reversed)")
    print("  Cross-validated against direct O(N^2) DFT and against NumPy")
    print("=" * 74)

    rng = np.random.default_rng(seed=20260814)

    sizes = [8, 16, 32, 64, 128, 256, 512, 1024]
    for N in sizes:
        ok = _run_size(N, rng, verbose=True)
        if not ok:
            print(f"\n[FAIL] at N = {N}")
            return 1

    print("\n" + "=" * 74)
    print(f"  All {len(sizes)} sizes passed.")
    print("  Sizes tested:", sizes)
    print("=" * 74)
    print("\nPASS!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
