# Phoenix SDR-DSP Milestones and Mathematics

## Project scope

`phoenix-sdr-dsp` develops deterministic DSP and finite-field kernels for the [AMD Ryzen 9 7940HS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) Phoenix NPU1, using its [XDNA1/AIE2](https://docs.kernel.org/accel/amdxdna/amdnpu.html) array through a native Windows [MLIR-AIE](https://github.com/Xilinx/mlir-aie)/[IRON](https://xilinx.github.io/mlir-aie/1.4.1/), [Peano](https://github.com/Xilinx/llvm-aie), and [XRT](https://github.com/Xilinx/XRT) workflow.

This reference documents M0 through M17p. A milestone is called **silicon-validated** only when its test runs on the physical NPU and checks the result against an independent CPU reference. An import failure, compiler failure, native assertion, or host-only calculation is not a silicon result.

## Notation and numerical policy

- `q = 3329` is the prime modulus used by the finite-field tests. It is the Kyber / [ML-KEM](https://csrc.nist.gov/pubs/fips/203/final) modulus: [NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) and the [CRYSTALS-Kyber round-3 specification](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf) both fix `(n, q) = (256, 3329)`.
- `N` is a transform length or polynomial dimension.
- `Z_q` denotes integers reduced modulo `q`.
- Canonical modular values are in `[0, q - 1]`.
- `j` is the imaginary unit, where `j^2 = -1`.
- DSP kernels use [`bfloat16`](https://cloud.google.com/blog/products/ai-machine-learning/bfloat16-the-secret-to-high-performance-on-cloud-tpus) inputs where stated (1 sign, 8 exponent, 7 explicit mantissa bits; same dynamic range as binary32, documented for AIE-ML in [AMD XAPP1406](https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats)); finite-field kernels use integer arithmetic; the M17 FFT uses complex `bfloat16` twiddles.

Validation rules:

- Every deterministic NPU kernel has an independent CPU reference.
- Modular arithmetic, NTTs, inverse NTTs, and polynomial multiplication must match the reference bit-for-bit.
- Fixed-point or `bfloat16` paths report a defined error measure such as maximum absolute error or SNR in dB.
- Test vectors include deterministic random inputs and structured cases appropriate to the operation.
- Transform roots, ordering, normalization, and reduction conventions are part of the test contract.

## Milestone map

| Milestone | Focus | Result |
|---|---|---|
| M0 | Windows environment audit | Development environment recorded |
| M1 | Native Windows architecture decision | Native execution workflow selected |
| M2 | Pinned local toolchain | MLIR-AIE, Peano, XRT, and Python environment configured |
| M3 | SAXPY vector kernel | Silicon-validated |
| M4 | LimeSDR enumeration and host streaming | Hardware integration milestone; outside automated regression |
| M5 | 8-tap FIR filter | Silicon-validated |
| M6 | Complex mixer / NCO | Silicon-validated |
| M7 | Power / RSSI detector | Silicon-validated |
| M8 | Fused DSP pipeline | Silicon-validated |
| M9 | Four-column parallel FIR | Silicon-validated |
| M9b | Four-column parallel multi-stage pipeline | Silicon-validated |
| M10 | Modular arithmetic and Barrett reduction | Silicon-validated, bit-exact |
| M11 | Radix-2 NTT butterfly | Silicon-validated, bit-exact |
| M12 | CPU NTT/INTT reference | Validated mathematical reference |
| M13 | Batched 16-point NPU NTT | Silicon-validated, bit-exact |
| M14 | Batched 256-point NPU NTT | Silicon-validated, bit-exact |
| M15 | INTT and cyclic polynomial multiplication | Silicon-validated, bit-exact |
| M15b | Negacyclic polynomial multiplication | Silicon-validated, bit-exact |
| M16 | CPU DFT/FFT reference | Validated mathematical reference |
| M17 | 64-point NPU radix-4 Stockham FFT and IFFT | Silicon-validated, SNR-bounded |
| M17p | Four-column parallel FFT channelizer | Silicon-validated |

The I/Q throughput demo in `tests/npu_visible/` is not a numbered milestone and is not in `run_all_silicon_tests.py`. It reuses the M6 complex-multiply contract on all four columns and reports host-visible MB/s / Msps.

## M0–M2: native Windows foundation

### M0 — Environment audit

M0 captures the machine and toolchain state required to reproduce the project: Windows version, Python environment, NPU target, compiler/tool paths, and runtime dependencies. It is a reproducibility step rather than a DSP kernel.

### M1 — Architecture decision

M1 selects the native Windows execution path for the Phoenix NPU. The goal is to retain explicit control of NPU compilation, host buffers, DMA submission, and output verification instead of treating deterministic DSP or NTT operations as neural-network inference.

### M2 — Pinned toolchain

M2 establishes the local `ironenv` Python environment and the MLIR-AIE, Peano, and XRT components used by subsequent tests. Pinning the local toolchain prevents an API or compiler update from silently changing kernel behavior. The current pin is upstream [mlir-aie v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1) at commit [`3ca0193`](https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22) (v1.4.1 + 13 commits, 2026-08-14, includes [PR #3545](https://github.com/Xilinx/mlir-aie/pull/3545)); when upstream breaks API compatibility, the ROADMAP's toolchain-events section documents the migration. Official native-Windows IRON path: [buildHostWinNative 1.4.1](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/).

## M3: SAXPY vector arithmetic

M3 establishes the basic NPU path with the [SAXPY](https://dl.acm.org/doi/10.1145/355841.355847) operation (`y ← a·x + y`, [Lawson, Hanson, Kincaid, and Krogh, ACM TOMS 1979](https://netlib.org/blas/saxpy.f)):

```text
y[i] = a * x[i] + y[i]
```

Here, `a` is a scalar and `x` and `y` are vectors. The test uses `bfloat16` vector data and compares NPU output against a host reference. This validates compilation, device loading, buffer movement, kernel execution, result retrieval, and numerical comparison.

SAXPY is foundational because it exercises vector multiplication and addition, which recur in filtering, mixing, correlations, and many linear DSP blocks.

## M4: LimeSDR host integration

M4 covers [LimeSDR](https://limemicro.com/products/boards/limesdr/) enumeration and host-side streaming preparation. It is intentionally separate from the NPU regression runner because it depends on attached RF hardware, driver state, and a legal local RF test configuration.

The target receive-side structure is conceptually:

```text
LimeSDR receive -> host buffer/ring -> NPU submission -> DSP result -> application consumer
```

A production streaming path should track overrun, underrun, dropped samples, timestamp discontinuities, transfer errors, queue depth, and end-to-end latency.

## M5: 8-tap vectorized FIR filter

A finite impulse response filter with eight coefficients is ([Smith, *The Scientist and Engineer's Guide to DSP*, ch. 14](https://www.dspguide.com/ch14.htm))

```text
y[n] = sum(k = 0 to 7) h[k] * x[n-k]
```

where `h[k]` is the filter impulse response. The current output depends on the present sample and seven prior samples. FIR filters are stable by construction because they have no feedback path ([Smith, DSP Guide, ch. 14](https://www.dspguide.com/ch14.htm)).

In SDR processing, a low-pass FIR can reject adjacent-channel energy after downconversion, shape a passband, and suppress high-frequency image components. The M5 test compares NPU output to a reference and reports the maximum absolute error attributable to finite-precision `bfloat16` arithmetic.

Important implementation details:

- Input and coefficient ordering must agree between NPU and CPU references.
- Startup samples require a stated history/zero-padding policy.
- Fixed-point scale and rounding rules affect measured error.
- A vectorized implementation must preserve the scalar convolution result.

## M6: complex mixer and NCO

A complex baseband sample is

```text
x[n] = I[n] + jQ[n]
```

A numerically controlled oscillator produces a phasor ([Analog Devices MT-085](https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf))

```text
lo[n] = cos(theta[n]) + j sin(theta[n])
theta[n+1] = theta[n] + Delta_theta
```

The mixer computes

```text
y[n] = x[n] * lo[n]
```

or, by separating real and imaginary components,

```text
I_y[n] = I_x[n]I_lo[n] - Q_x[n]Q_lo[n]
Q_y[n] = I_x[n]Q_lo[n] + Q_x[n]I_lo[n]
```

Complex multiplication translates spectrum by the oscillator frequency ([Lyons / Analog Devices complex-mixer identity](https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf)). Choosing the phasor sign consistently determines whether the operation is interpreted as upconversion or downconversion. M6 checks the mixed I/Q samples against the CPU reference and reports the maximum absolute error.

The optional `tests/npu_visible/test_iq_throughput.py` demo applies the same mix across four columns with many 1024-element frames per dispatch. On 2026-08-15 a Ryzen 9 7940HS Phoenix NPU1 ([10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html)) measured **7.459 Msps** / 29.84 MB/s I/Q in, first-buffer $L_\infty = 0.007812$. That rate is host-visible IRON + shim DMA, not a theoretical AIE peak. Kernel vectorization is deferred.

## M7: power and RSSI estimation

For complex samples, instantaneous power is

```text
p[n] = |x[n]|^2 = I[n]^2 + Q[n]^2
```

No square root is required for energy detection, so the result is efficient and preserves ordering: if one signal has greater magnitude than another, it also has greater magnitude squared ([Smith, DSP Guide, ch. 11, RMS / magnitude](https://www.dspguide.com/ch11.htm)). Typical uses include RSSI-like estimation, activity detection, carrier-presence detection, and thresholding.

If a decibel value is needed later, it is calculated from a suitably averaged positive power estimate:

```text
P_dB = 10 * log10(P / P_ref)     # IEC 60027-3 / common power ratio; see NIST SP 330
```

M7 validates the NPU output array against its CPU calculation.

## M8: fused SDR demodulator pipeline

M8 composes earlier kernels into one streaming DSP chain:

```text
complex IQ -> NCO downconversion -> dual-channel FIR -> power detector
```

For each block, the NCO frequency-translates the desired signal, FIR stages filter I and Q components, and the detector produces magnitude-squared output. A fused path minimizes round trips through host memory between individual stages and checks that stage ordering, data layout, and scaling remain consistent.

Correctness requirements include:

- Consistent interleaved I/Q sample layout.
- Equal filter history policy on CPU and NPU.
- Explicit NCO phase convention.
- Preserved block ordering and output length.
- Reference comparison after the complete pipeline, not only per-stage inspection.

## M9: four-column parallel FIR

M9 scales FIR work over all four Phoenix NPU columns ([Linux `amdxdna` topology: Phoenix/Hawk Point is a 4×5 XDNA1 array](https://docs.kernel.org/accel/amdxdna/amdnpu.html)). The filter equation remains

```text
y[n] = sum(k = 0 to 7) h[k] * x[n-k]
```

but the input work is partitioned across columns. Correctness depends on handling block boundaries: an output near a partition edge may need samples from the previous partition because an FIR kernel has history. The parallel output must be assembled in the original sample order and compared with one global CPU reference.

This milestone validates that hardware parallelism does not alter the filter result.

## M9b: four-column parallel multi-stage pipeline

M9b runs the M8 demodulator pipeline (mixer → FIR → power) on all four columns of the AIE2 grid, with independent per-column DMA supplied by a `TaskGroup` inside the sequence body. Each column processes a 2048-sample I/Q burst.

M9b reports throughput as `microseconds per burst` and derived megasamples per second. The verification contract is identical to M8: the parallel output must be assembled in sample order and match the CPU reference of the full pipeline.

## M10: modular arithmetic and Barrett reduction

M10 introduces arithmetic in the finite field `Z_3329`:

```text
add_q(a, b) = (a + b) mod 3329
sub_q(a, b) = (a - b) mod 3329
mul_q(a, b) = (a * b) mod 3329
```

Canonical correction can be expressed as:

```text
if r >= q: r = r - q
if r < 0:  r = r + q
```

after an addition or subtraction whose range is known.

[Barrett reduction](https://link.springer.com/chapter/10.1007/3-540-47721-7_24) avoids division in modular multiplication ([Barrett, CRYPTO 1986](https://link.springer.com/chapter/10.1007/3-540-47721-7_24)). For a selected shift `s`, precompute an approximation

```text
mu = floor(2^s / q)
```

For a nonnegative intermediate `x`, estimate the quotient and residual:

```text
t = floor(x * mu / 2^s)
r = x - t * q
```

Then correct `r` into `[0, q-1]`. The approximation makes `t` close to `floor(x/q)`; correction removes the remaining bounded error. M10 confirms all reported modular results exactly match CPU `% q` arithmetic.

## M11: radix-2 NTT butterfly

An NTT is the finite-field analogue of a discrete Fourier transform ([Kyber spec §1.1](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf); [PLOS ONE Kyber NTT](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0323224)). A radix-2 [Cooley–Tukey](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf) butterfly (Gentleman–Sande DIF is the dual form, [AFIPS 1966](https://dl.acm.org/doi/10.1145/1464291.1464352)) takes values `u`, `v`, and a twiddle factor `w`:

```text
t  = w * v mod q
u' = u + t mod q
v' = u - t mod q
```

Repeated butterflies rearrange and combine a vector into its transform-domain representation. Every multiply, add, and subtract is reduced modulo `q`. M11 validates batches of butterflies bit-exactly against the same formula on the CPU.

## M12: NTT/INTT mathematical reference

M12 supplies the independent CPU source of truth for the NPU NTT tests.

For an N-point transform, a primitive N-th root of unity `omega` must satisfy:

```text
omega^N = 1 mod q
omega^(N/p) != 1 mod q for every prime divisor p of N   # primitive N-th root of unity in Z_q; Kyber uses a 256-th root in Z_3329, [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)
```

The forward transform convention is

```text
X[k] = sum(n = 0 to N-1) x[n] * omega^(n*k) mod q
```

The inverse transform is

```text
x[n] = N^(-1) * sum(k = 0 to N-1) X[k] * omega^(-n*k) mod q
```

where `N^(-1)` satisfies

```text
N * N^(-1) = 1 mod q
```

Validated parameter values are:

| Transform length `N` | Modulus `q` | `omega` | `omega^(-1)` | `N^(-1) mod q` |
|---:|---:|---:|---:|---:|
| 16 | 3329 | 2699 | 1897 | 3121 |
| 256 | 3329 | 3061 | 2298 | 3316 |

The reference suite checks prime-modulus assumptions, root order, inverse normalization, impulse behavior, constant-vector behavior, direct-transform agreement for random vectors, and exact round-trip recovery:

```text
INTT(NTT(x)) = x
```

The iterative radix-2 implementation must state its ordering convention. A decimation-in-time implementation typically consumes bit-reversed input or produces bit-reversed output depending on the surrounding permutation. The NPU and CPU must use exactly the same convention before outputs are compared.

## M13: batched 16-point NPU NTT

M13 runs 64 independent NTT frames of length 16, for 1024 coefficients per test run. The workload includes structured inputs and random input frames:

- An impulse should transform to all ones.
- A constant vector should place its energy in the DC bin and yield zero in non-DC bins under the stated convention.
- Random vectors must match the M12 CPU transform coefficient-for-coefficient.

Batching verifies that frame boundaries, buffer offsets, and repeated kernel execution do not corrupt neighboring transforms.

## M14: batched 256-point NPU NTT

M14 applies the same verification approach at `N = 256`, with four frames totaling 1024 coefficients. The transform uses

```text
q = 3329
omega = 3061
omega^(-1) = 2298
N^(-1) = 3316
```

The milestone verifies impulse, constant, and random frames exactly. This confirms that the full butterfly schedule, twiddle indexing, modular reduction, memory layout, and output order all agree with M12 at the larger transform length.

## M15: inverse NTT and cyclic polynomial multiplication

M15 completes the cyclic NTT multiplication workflow in

```text
Z_3329[x] / (x^256 - 1)
```

A polynomial is

```text
A(x) = A[0] + A[1]x + ... + A[N-1]x^(N-1)
```

Cyclic multiplication wraps powers with a positive sign because `x^N = 1`:

```text
C[k] = sum(i + j congruent to k mod N) A[i] * B[j] mod q
```

The NTT convolution identity (cyclic convolution theorem; [Stockham, AFIPS 1966](https://dl.acm.org/doi/10.1145/1464182.1464209)) is

```text
C = INTT(NTT(A) elementwise_multiply NTT(B))
```

with all operations in `Z_3329`. M15 verifies both requirements:

1. Exact inverse-transform round trip, where recovered `A` equals the original input.
2. Exact cyclic polynomial product, where the NPU result equals a direct CPU cyclic-convolution reference.

This check is important because a transform can appear correct on isolated vectors while still failing due to inverse normalization, twiddle ordering, pointwise-product placement, or cyclic wraparound errors.

## M15b: negacyclic polynomial multiplication

M15b targets the negacyclic ring — the Kyber / ML-KEM ring `R_q = Z_q[x]/(x^n+1)` ([FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf); [Kyber spec](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf); [Isabelle/AFP CRYSTALS-Kyber](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf)) — where `x^N = -1`:

```text
Z_3329[x] / (x^256 + 1)
```

Negacyclic convolution via NTT requires pre-multiplication of both operands by powers of a `2N`-th root of unity `psi`, forward NTT of the twisted operands, pointwise multiplication, inverse NTT, and post-multiplication by `psi^(-k)` ([Kyber spec, NTT section](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf); [FIPS 203 §4](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)). The composed operation gives the negacyclic product.

The silicon-validated M15b kernel is a schoolbook O(N²) product in that ring (the definition of multiplication in `Z_q[x]`; not the NTT form), checked bit-exact against an independent CPU reference (`negacyclic_polymul_ref`, seed 42). Modular reduction uses [Barrett](https://link.springer.com/chapter/10.1007/3-540-47721-7_24) with the inherited kernel constants `MU = 20165`, shift 26 (do not silently replace with M15's `20158 = floor(2^26/3329)`). The host driver uses the same [`iron.Runtime(seq_fn)`](https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py) sequence-function API as M15 ([mlir-aie v1.4.1](https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1)). An NTT-based negacyclic path (FIPS 203 Algorithms 9–12) is **M32**, not this milestone. Validated 2026-08-15 on Phoenix NPU1.

## M32: FIPS 203 ML-KEM (planned)

M32 is an extra milestone after M10–M15b. It implements the approved key-encapsulation mechanism in [NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) (*Module-Lattice-Based Key-Encapsulation Mechanism Standard*, 13 August 2024, [DOI 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203)). ML-KEM is derived from round-3 [CRYSTALS-Kyber](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf) (FIPS 203 §1.1); implement FIPS 203 when Appendix C lists a difference.

The three approved parameter sets ([FIPS 203 Table 2](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)) all use `(n, q) = (256, 3329)`:

| Set | k | η1 | η2 | du | dv |
|---|---:|---:|---:|---:|---:|
| ML-KEM-512 | 2 | 3 | 2 | 10 | 4 |
| ML-KEM-768 | 3 | 2 | 2 | 10 | 4 |
| ML-KEM-1024 | 4 | 2 | 2 | 11 | 5 |

First target is ML-KEM-512. NIST's default recommendation is ML-KEM-768 (FIPS 203 §8). Hashes are [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) SHA3-256, SHA3-512, SHAKE128, and SHAKE256 (FIPS 203 §4.1). K-PKE (Algorithms 13–15) is a component only and is not approved as a standalone PKE (FIPS 203 §3.3).

Gates, pass criteria, and the algorithm table live in [`M32_FIPS203_MLKEM.md`](M32_FIPS203_MLKEM.md). M32 is not an entry in the 16-test silicon runner.

## M16: CPU DFT/FFT mathematical reference

M16 supplies the independent CPU source of truth for the NPU FFT tests. It ships three independent implementations that must agree with each other and with [`numpy.fft.fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html) to double-precision round-off:

1. Direct O(N^2) DFT via an `N` by `N` twiddle matrix:

```text
W[k, n] = exp(-2 pi j * k * n / N)
X = W @ x
```

2. Recursive radix-2 [Cooley–Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf), splitting `x` into even and odd sub-sequences and combining:

```text
X[k]         = E[k] + W_N^k * O[k]
X[k + N/2]   = E[k] - W_N^k * O[k]
```

3. Iterative in-place radix-2 with bit-reversed permutation. This is the dataflow proxy for the M17 NPU butterfly kernel.

The test suite covers impulse, DC constant, pure tone, random complex vectors, [Parseval](https://mathworld.wolfram.com/ParsevalsTheorem.html) energy conservation, and the round-trip identity `x = IFFT(FFT(x))` ([NumPy `ifft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.ifft.html)), for sizes `N` in `{8, 16, 32, 64, 128, 256, 512, 1024}`. All three implementations agree with NumPy to about 10^-13 relative error, consistent with the O(log N)·ε bound in [Higham, *Accuracy and Stability of Numerical Algorithms*, 2nd ed., SIAM 2002, §24.1](https://doi.org/10.1137/1.9780898718027). M16 runs on Ubuntu in CI in about 0.3 seconds.

## M17: 64-point NPU radix-4 Stockham FFT

M17 is a 64-point complex-`bfloat16` FFT on a single AIE2 tile. The algorithm is a radix-4 [Stockham auto-sort](https://dl.acm.org/doi/10.1145/1464182.1464209) FFT ([Stockham, AFIPS 1966](https://dl.acm.org/doi/pdf/10.1145/1464182.1464209)), which interleaves the butterfly and shuffle stages so that the output of each stage is already in natural order and no bit-reversed permutation is required. The silicon kernel is adapted from AMD [`FFT_R4_AIE`](https://github.com/diacccc/FFT_R4_AIE) (Apache-2.0).

For a radix-4 Stockham stage at stride `L`, each quadruplet `(a, b, c, d)` produces four outputs using pre-computed twiddles `W1`, `W2`, `W3`:

```text
t0 = a + c
t1 = a - c
t2 = b + d
t3 = j * (b - d)

a' = t0 + t2
b' = W1 * (t1 - t3)
c' = W2 * (t0 - t2)
d' = W3 * (t1 + t3)
```

Three radix-4 stages recover a 64-point transform, because `4 * 4 * 4 = 64`. The shipped kernel uses complex-`bfloat16` twiddles laid out in local L1 memory. Measured against `numpy.fft.fft`, the forward FFT achieves an SNR of about 138.79 dB, which exceeds the double-precision noise floor for a 64-point transform and confirms that the twiddle precision and stage schedule are correct.

M17 does not ship a separate inverse-FFT kernel. The host driver uses the identity

```text
IFFT(Y) = conj( FFT( conj(Y) ) ) / N
```

so the same forward kernel serves both directions. Round-trip RMS SNR on random complex vectors is about 135.11 dB.

## M17p: four-column parallel FFT channelizer

M17p runs the M17 radix-4 Stockham kernel across all four AIE2 tile columns of the Phoenix NPU1 grid ([Linux `amdxdna` 4×5 Phoenix topology](https://docs.kernel.org/accel/amdxdna/amdnpu.html)). Each column receives its own 64-point frame via an independent per-column `TaskGroup`, so 64 parallel frames complete per burst.

Measured throughput on Phoenix NPU1 is about 1,993 FFTs per second, or about 0.51 MB/s of I/Q sample stream. M17p uses the same code path a future channelizer or streaming spectrum analyzer would use, and validates that hardware parallelism does not alter the transform result.

## Automated regression coverage

`run_all_silicon_tests.py` executes 16 automated test entries:

```powershell
python run_all_silicon_tests.py
```

The runner reports pass/fail status and elapsed time for:

1. M3   SAXPY
2. M5   FIR
3. M6   complex mixer/NCO
4. M7   power detector
5. M8   fused pipeline
6. M9   four-column FIR
7. M9b  four-column multi-stage pipeline
8. M10  modular arithmetic
9. M11  NTT butterfly
10. M12  CPU NTT reference
11. M13  16-point NTT
12. M14  256-point NTT
13. M15  INTT and cyclic polynomial multiplication
14. M15b negacyclic polynomial multiplication
15. M17  radix-4 Stockham FFT and IFFT
16. M17p four-column parallel FFT

M0–M2 are setup and reproducibility milestones, while M4 depends on locally attached SDR hardware; therefore they are not entries in the automated silicon regression runner.

## Practical verification checklist

Before calling a deterministic kernel complete:

- Confirm the target device is the physical Phoenix NPU.
- Keep the CPU reference independent from the NPU kernel implementation.
- Fix the random seed for reproducible failures.
- Test zeros, impulses, constants, boundary modular values, and random vectors.
- Check exact output shape, buffer offsets, ordering, and batch boundaries.
- For fixed-point and `bfloat16` DSP, document scaling, rounding, saturation, and the accepted tolerance.
- For NTTs, document `N`, `q`, root values, inverse values, forward/inverse convention, ordering, bit-reversal, and normalization.
- For complex FFTs, document the auto-sort schedule, twiddle layout, and SNR floor being claimed.
- Record timing separately from correctness; a correct result is not automatically a throughput claim.


## References

### Hardware

- AMD, "AMD Ryzen™ 9 7940HS" — Phoenix NPU rated up to 10 TOPS. https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html
- Tom's Hardware, "The refresh that wasn't — AMD announces Hawk Point Ryzen 8040" (2023-12-06) — XDNA1 delivers 10 TOPS INT8 on Phoenix 7040. https://www.tomshardware.com/pc-components/cpus/the-refresh-that-wasnt-amd-announces-hawk-point-ryzen-8040-series-with-zen-4-rdna3-and-xdna-teases-strix-point
- The Linux Kernel, "AMD NPU" — XDNA1 4×5 topology and the `amdxdna` driver. https://docs.kernel.org/accel/amdxdna/amdnpu.html
- AMD, "Floating-Point Numerical Formats" (XAPP1406) — bfloat16 on AIE-ML. https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats
- Google Cloud, "BFloat16: The secret to high performance on Cloud TPUs" (2019). https://cloud.google.com/blog/products/ai-machine-learning/bfloat16-the-secret-to-high-performance-on-cloud-tpus
- Lime Microsystems, LimeSDR. https://limemicro.com/products/boards/limesdr/

### Toolchain

- Xilinx/AMD, MLIR-AIE. https://github.com/Xilinx/mlir-aie
- IRON / MLIR-AIE documentation v1.4.1. https://xilinx.github.io/mlir-aie/1.4.1/
- Native Windows IRON guide v1.4.1. https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
- mlir-aie v1.4.1 release. https://github.com/Xilinx/mlir-aie/releases/tag/v1.4.1
- mlir-aie commit `3ca0193` (PR #3545, `run_chain` lifetime). https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22
- `iron.Runtime` at the pin. https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py
- Xilinx/AMD, llvm-aie (Peano). https://github.com/Xilinx/llvm-aie
- Xilinx/AMD, XRT. https://github.com/Xilinx/XRT
- XRT Windows SDK 2.21.75. https://github.com/Xilinx/XRT/releases/tag/2.21.75
- AMD, FFT_R4_AIE radix-4 Stockham reference (Apache-2.0). https://github.com/diacccc/FFT_R4_AIE

### DSP and FFT

- C. L. Lawson, R. J. Hanson, D. R. Kincaid, F. T. Krogh, "Basic Linear Algebra Subprograms for Fortran Usage", *ACM TOMS* 5(3):308–323 (1979) — SAXPY. https://dl.acm.org/doi/10.1145/355841.355847
- S. W. Smith, *The Scientist and Engineer's Guide to Digital Signal Processing*, ch. 14 (FIR). https://www.dspguide.com/ch14.htm
- Analog Devices, MT-085, "Fundamentals of Direct Digital Synthesis (DDS)" — NCO / complex mixing. https://www.analog.com/media/en/training-seminars/tutorials/MT-085.pdf
- J. W. Cooley and J. W. Tukey, "An algorithm for the machine calculation of complex Fourier series", *Math. Comput.* 19:297–301 (1965). https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf
- T. G. Stockham, Jr., "High-speed convolution and correlation", AFIPS Spring Joint Computer Conference (1966). https://dl.acm.org/doi/10.1145/1464182.1464209
- W. M. Gentleman and G. Sande, "Fast Fourier Transforms — for fun and profit", AFIPS Fall Joint Computer Conference (1966). https://dl.acm.org/doi/10.1145/1464291.1464352
- N. J. Higham, *Accuracy and Stability of Numerical Algorithms*, 2nd ed., SIAM (2002), §24.1. https://doi.org/10.1137/1.9780898718027
- Parseval's theorem. https://mathworld.wolfram.com/ParsevalsTheorem.html
- NumPy `numpy.fft.fft` / `ifft`. https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html
- K. Ozaki, T. Ogita, S. Oishi, S. M. Rump, "Error-free transformations of matrix multiplication by using fast routines of matrix multiplication and its applications", *Numerical Algorithms* 59:95–118 (2012). https://doi.org/10.1007/s11075-011-9478-1

### Finite fields, NTT, Kyber / ML-KEM

- P. Barrett, "Implementing the Rivest Shamir and Adleman Public Key Encryption Algorithm on a Standard Digital Signal Processor", CRYPTO 1986. https://link.springer.com/chapter/10.1007/3-540-47721-7_24
- NIST, FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (2024-08-13). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 203 landing page. https://csrc.nist.gov/pubs/fips/203/final
- NIST, FIPS 202, *SHA-3 Standard* (2015). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
- NIST Post-Quantum Cryptography project. https://csrc.nist.gov/projects/post-quantum-cryptography
- NIST CAVP. https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program
- Avanzi et al., *CRYSTALS-Kyber* Algorithm Specification, version 3.02 (2021-08-04). https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf
- Isabelle/AFP, "δ-Correctness Proof of CRYSTALS-KYBER" — formalization of `Z_q[x]/(x^N+1)`. https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf
- "Area-time efficient pipelined number theoretic transform for CRYSTALS-Kyber", *PLOS ONE* (2025). https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0323224
