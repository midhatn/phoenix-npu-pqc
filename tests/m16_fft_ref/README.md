# M16 — CPU FFT/IFFT Reference

Independent, hardware-free CPU reference for the discrete Fourier transform
and its inverse. This directory is the FFT counterpart of `tests/m12_ntt_ref/`:
it serves as the ground-truth oracle against which the NPU FFT kernel (M17)
will be bit-checked once implemented.

## Contents

- `test_fft_reference_m16.py` — three cross-validated implementations of the
  length-N complex DFT/IDFT, plus a self-contained test battery.

## Implementations

| Name | Algorithm | Complexity | Purpose |
|---|---|---|---|
| `direct_dft` | Twiddle matrix multiplication, eqn. (1) | O(N²) | Mathematical ground truth. No optimizations. |
| `direct_idft` | Twiddle matrix multiplication, eqn. (2) | O(N²) | Inverse ground truth. |
| `radix2_fft_recursive` | Recursive [Cooley-Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf) DIT | O(N log N) | Closest one-to-one Python transcription of the [CT65] recurrence. |
| `radix2_fft_iterative` | Iterative in-place with bit-reversed permutation | O(N log N) | Dataflow proxy for the M17 NPU butterfly kernel. |
| `radix2_ifft_recursive` | `IFFT(X) = conj(FFT(conj(X))) / N` | O(N log N) | Inverse via the standard identity ([NumPy `ifft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.ifft.html)). |

## Test battery

At each size N ∈ {8, 16, 32, 64, 128, 256, 512, 1024}:

1. **Unit impulse** — DFT of `[1, 0, …, 0]` must equal `[1, 1, …, 1]`.
2. **DC constant** — DFT of `[c, c, …, c]` must concentrate energy at bin 0.
3. **Pure tone** — DFT of `exp(2πj·k₀·n/N)` must concentrate energy at bin k₀.
4. **Random complex vector** — all three FFT implementations must agree with
   the direct DFT and with NumPy's `fft.fft` to relative L2 error ≤ 1e-11.
5. **Round-trip** — `x == IFFT(FFT(x))` to relative L2 error ≤ 1e-11
   (typically ~1e-16).
6. **[Parseval](https://mathworld.wolfram.com/ParsevalsTheorem.html) / Plancherel** — energy conservation:
   `Σ|x[n]|² = (1/N) · Σ|X[k]|²`, relative error ≤ 1e-12
   (typically zero at double precision).

## Running

Locally (Windows or Linux):

```bash
python tests/m16_fft_ref/test_fft_reference_m16.py
```

Expected wall time: ~0.3 s on modern x86_64. Exit code 0 with terminal
`PASS!` on success.

This test is also wired into the CI job `cpu-reference-tests` so it runs
on every push to `main` and every pull request.

## Mathematical background

For a length-N complex input vector `x[0..N-1]`, the forward DFT is

    X[k] = Σₙ x[n] · exp(-j·2π·k·n / N),    k = 0 … N-1

and the inverse DFT is

    x[n] = (1/N) · Σₖ X[k] · exp(+j·2π·k·n / N),    n = 0 … N-1

The direct evaluation is O(N²). For N = 2^m the sum can be split recursively
into two half-length transforms of the even- and odd-indexed samples,
yielding the O(N log₂ N) radix-2 decimation-in-time Cooley-Tukey algorithm
([CT65], [Rice], [McFee]).

### Numerical stability

The recursive radix-2 FFT accumulates O(log₂ N) round-off. Its relative L2
error is bounded by a small multiple of `log₂(N) · ε_machine`. For
`complex128` (ε ≈ 2.22 × 10⁻¹⁶) and N ≤ 1024, the expected relative error
against a direct DFT is on the order of 10⁻¹³ — which the test tolerance
(`1e-11`) comfortably covers.

## References

- **[CT65]** Cooley, J. W. and Tukey, J. W. (1965). "An algorithm for the
  machine calculation of complex Fourier series."
  *Mathematics of Computation* 19(90): 297–301.
  [PDF reprint](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf).
- **[Rice]** Rice University FFT tutorial (public):
  https://repository.rice.edu/server/api/core/bitstreams/01e9e0a5-fa6f-453d-a1b5-8209fa0a565c/content
- **[McFee]** McFee, B. *Digital Signals Theory*, §8.2 Fast Fourier Transform:
  https://brianmcfee.net/dstbook-site/content/ch08-fft/FFT.html
- **[NumPy]** NumPy `numpy.fft.fft` documentation:
  https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html
- **Higham, N. J.** (2002). *Accuracy and Stability of Numerical Algorithms*,
  2nd ed., §24.1 (FFT round-off bounds). SIAM.
  [DOI 10.1137/1.9780898718027](https://doi.org/10.1137/1.9780898718027).
