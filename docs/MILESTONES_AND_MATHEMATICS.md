# Phoenix SDR-DSP Milestones and Mathematics

## Project scope

`phoenix-sdr-dsp` develops deterministic DSP and finite-field kernels for the AMD Ryzen 9 7940HS Phoenix NPU1, using its XDNA1/AIE2 array through a native Windows MLIR-AIE, Peano, and XRT workflow.

This reference documents M0 through M15 only. A milestone is called **silicon-validated** only when its test runs on the physical NPU and checks the result against an independent CPU reference. An import failure, compiler failure, native assertion, or host-only calculation is not a silicon result.

## Notation and numerical policy

- `q = 3329` is the prime modulus used by the finite-field tests.
- `N` is a transform length or polynomial dimension.
- `Z_q` denotes integers reduced modulo `q`.
- Canonical modular values are in `[0, q - 1]`.
- `j` is the imaginary unit, where `j^2 = -1`.
- DSP kernels use `bfloat16` inputs where stated; finite-field kernels use integer arithmetic.

Validation rules:

- Every deterministic NPU kernel has an independent CPU reference.
- Modular arithmetic, NTTs, inverse NTTs, and polynomial multiplication must match the reference bit-for-bit.
- Fixed-point or `bfloat16` paths report a defined error measure such as maximum absolute error.
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
| M10 | Modular arithmetic and Barrett reduction | Silicon-validated, bit-exact |
| M11 | Radix-2 NTT butterfly | Silicon-validated, bit-exact |
| M12 | CPU NTT/INTT reference | Validated mathematical reference |
| M13 | Batched 16-point NPU NTT | Silicon-validated, bit-exact |
| M14 | Batched 256-point NPU NTT | Silicon-validated, bit-exact |
| M15 | INTT and cyclic polynomial multiplication | Silicon-validated, bit-exact |

## M0–M2: native Windows foundation

### M0 — Environment audit

M0 captures the machine and toolchain state required to reproduce the project: Windows version, Python environment, NPU target, compiler/tool paths, and runtime dependencies. It is a reproducibility step rather than a DSP kernel.

### M1 — Architecture decision

M1 selects the native Windows execution path for the Phoenix NPU. The goal is to retain explicit control of NPU compilation, host buffers, DMA submission, and output verification instead of treating deterministic DSP or NTT operations as neural-network inference.

### M2 — Pinned toolchain

M2 establishes the local `ironenv` Python environment and the MLIR-AIE, Peano, and XRT components used by subsequent tests. Pinning the local toolchain prevents an API or compiler update from silently changing kernel behavior.

## M3: SAXPY vector arithmetic

M3 establishes the basic NPU path with the SAXPY operation:

```text
y[i] = a * x[i] + y[i]
```

Here, `a` is a scalar and `x` and `y` are vectors. The test uses `bfloat16` vector data and compares NPU output against a host reference. This validates compilation, device loading, buffer movement, kernel execution, result retrieval, and numerical comparison.

SAXPY is foundational because it exercises vector multiplication and addition, which recur in filtering, mixing, correlations, and many linear DSP blocks.

## M4: LimeSDR host integration

M4 covers LimeSDR enumeration and host-side streaming preparation. It is intentionally separate from the NPU regression runner because it depends on attached RF hardware, driver state, and a legal local RF test configuration.

The target receive-side structure is conceptually:

```text
LimeSDR receive -> host buffer/ring -> NPU submission -> DSP result -> application consumer
```

A production streaming path should track overrun, underrun, dropped samples, timestamp discontinuities, transfer errors, queue depth, and end-to-end latency.

## M5: 8-tap vectorized FIR filter

A finite impulse response filter with eight coefficients is

```text
y[n] = sum(k = 0 to 7) h[k] * x[n-k]
```

where `h[k]` is the filter impulse response. The current output depends on the present sample and seven prior samples. FIR filters are stable by construction because they have no feedback path.

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

A numerically controlled oscillator produces a phasor

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

Complex multiplication translates spectrum by the oscillator frequency. Choosing the phasor sign consistently determines whether the operation is interpreted as upconversion or downconversion. M6 checks the mixed I/Q samples against the CPU reference and reports the maximum absolute error.

## M7: power and RSSI estimation

For complex samples, instantaneous power is

```text
p[n] = |x[n]|^2 = I[n]^2 + Q[n]^2
```

No square root is required for energy detection, so the result is efficient and preserves ordering: if one signal has greater magnitude than another, it also has greater magnitude squared. Typical uses include RSSI-like estimation, activity detection, carrier-presence detection, and thresholding.

If a decibel value is needed later, it is calculated from a suitably averaged positive power estimate:

```text
P_dB = 10 * log10(P / P_ref)
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

M9 scales FIR work over all four Phoenix NPU columns. The filter equation remains

```text
y[n] = sum(k = 0 to 7) h[k] * x[n-k]
```

but the input work is partitioned across columns. Correctness depends on handling block boundaries: an output near a partition edge may need samples from the previous partition because an FIR kernel has history. The parallel output must be assembled in the original sample order and compared with one global CPU reference.

This milestone validates that hardware parallelism does not alter the filter result.

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

Barrett reduction avoids division in modular multiplication. For a selected shift `s`, precompute an approximation

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

An NTT is the finite-field analogue of a discrete Fourier transform. A radix-2 Cooley-Tukey butterfly takes values `u`, `v`, and a twiddle factor `w`:

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
omega^(N/p) != 1 mod q for every prime divisor p of N
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

The NTT convolution identity is

```text
C = INTT(NTT(A) elementwise_multiply NTT(B))
```

with all operations in `Z_3329`. M15 verifies both requirements:

1. Exact inverse-transform round trip, where recovered `A` equals the original input.
2. Exact cyclic polynomial product, where the NPU result equals a direct CPU cyclic-convolution reference.

This check is important because a transform can appear correct on isolated vectors while still failing due to inverse normalization, twiddle ordering, pointwise-product placement, or cyclic wraparound errors.

## Automated regression coverage

`run_all_silicon_tests.py` executes the automated test entries for M3 and M5 through M15:

```powershell
python run_all_silicon_tests.py
```

The runner reports pass/fail status and elapsed time for twelve tests:

1. M3 SAXPY
2. M5 FIR
3. M6 complex mixer/NCO
4. M7 power detector
5. M8 fused pipeline
6. M9 four-column FIR
7. M10 modular arithmetic
8. M11 NTT butterfly
9. M12 CPU NTT reference
10. M13 16-point NTT
11. M14 256-point NTT
12. M15 INTT and cyclic polynomial multiplication

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
- Record timing separately from correctness; a correct result is not automatically a throughput claim.
