# Phoenix SDR-DSP Milestones and Mathematics

## Scope and status

This document records the validated development milestones for `phoenix-sdr-dsp`, the mathematical models used by the DSP and number-theoretic workloads, and the boundary of the current implementation.

The target platform is the AMD Ryzen 9 7940HS Phoenix NPU1, using XDNA1/AIE2 through the native Windows MLIR-AIE, Peano, and XRT workflow. A result is described as **silicon-validated** only when the corresponding test executes on the physical NPU and compares its output with an independent CPU reference.

Milestone 16 is deliberately **not validated**. Work on it is paused after an MLIR-AIE graph-construction assertion. It must not be represented as a completed feature or a silicon result.

## Notation

- `q = 3329` is the prime modulus used by the finite-field tests.
- `N` is a transform length or polynomial degree.
- Arithmetic written modulo `q` is performed in the finite field `Z_q`.
- A vector or polynomial coefficient is represented as an integer in `[0, q-1]` after canonical reduction.
- Tests use deterministic input generation and CPU references so an NPU result can be checked exactly when integer arithmetic is expected to be exact.

## Environment milestones

| Milestone | Purpose | Deliverable | Validation status |
|---|---|---|---|
| M0 | Windows and WSL2 environment audit | Recorded toolchain and platform inventory | Setup milestone |
| M1 | Toolchain architecture decision | Native Windows runtime with any required compilation support selected | Setup milestone |
| M2 | Pinned development toolchain | `ironenv`, MLIR-AIE, Peano, XRT, and associated paths configured | Setup milestone |
| M3 | First native Windows MLIR-AIE execution | SAXPY kernel on Phoenix NPU | Silicon-validated |
| M4 | LimeSDR enumeration and host streaming | Device/host streaming integration work | Hardware-dependent; not part of the automated regression runner |

## Silicon-validated DSP milestones

### M3 — SAXPY vector operation

The M3 kernel computes a vector multiply-accumulate of the form

```
y[i] = a * x[i] + y[i]
```

for a scalar `a` and vector elements represented as `bfloat16`. It establishes the full compile, load, DMA, execute, and host-reference verification path on the Phoenix NPU.

### M5 — 8-tap vectorized FIR filter

The finite impulse response filter is

```
y[n] = sum(k = 0 to 7) h[k] * x[n-k]
```

where `h[k]` is the eight-tap coefficient sequence. This is the fundamental time-domain filtering primitive used to reject adjacent-band energy and shape a selected channel. The NPU output is compared with a host reference, allowing the bounded `bfloat16` quantization error reported by the test.

### M6 — Complex mixer and numerically controlled oscillator

Complex downconversion multiplies an input complex sample by a local oscillator:

```
x[n] = I[n] + j Q[n]
lo[n] = cos(theta[n]) + j sin(theta[n])
y[n] = x[n] * lo[n]
```

Equivalently,

```
I_y = I_x * I_lo - Q_x * Q_lo
Q_y = I_x * Q_lo + Q_x * I_lo
```

The phase is typically advanced as `theta[n+1] = theta[n] + Delta_theta`. Multiplication translates spectral content by the NCO frequency; choosing the opposite-sign phasor implements downconversion.

### M7 — Power and RSSI detector

For complex samples,

```
p[n] = I[n]^2 + Q[n]^2 = |x[n]|^2
```

This avoids a square root while preserving relative received energy. It is appropriate for RSSI-like estimation, energy detection, and threshold-based signal-presence logic.

### M8 — Fused SDR pipeline

M8 composes the preceding primitives as a streaming chain:

```
complex IQ -> NCO/mixer -> FIR filtering -> power detection
```

Conceptually, the NCO translates a target signal, the filter limits bandwidth, and the detector produces energy samples. Fusion reduces intermediate host transfers and verifies that stage ordering and scaling agree with the CPU model.

### M9 — Four-column parallel FIR

M9 partitions a FIR workload across the four-column NPU array. The filtering equation is unchanged from M5; the milestone verifies that partitioning and reassembly preserve the same reference output while exercising hardware scaling.

## Finite-field and NTT milestones

### M10 — Modular arithmetic and Barrett reduction

M10 validates modular addition, subtraction, multiplication, and canonical reduction modulo `q = 3329`.

```
add_q(a,b) = (a + b) mod q
sub_q(a,b) = (a - b) mod q
mul_q(a,b) = (a * b) mod q
```

Barrett reduction replaces an expensive division by a multiply-and-shift approximation. For a nonnegative value `x`, choose a precomputed constant approximately equal to `2^s / q`, estimate the quotient using a right shift, then correct the small residual into `[0, q-1]`. The exact correction policy must be verified against the CPU `% q` reference.

### M11 — Radix-2 NTT butterfly

Given coefficients `u`, `v`, and a twiddle factor `w`, a Cooley-Tukey radix-2 butterfly computes

```
t  = w * v mod q
u' = u + t mod q
v' = u - t mod q
```

The butterfly is the core operation of a radix-2 number-theoretic transform. M11 checks NPU output exactly against modular host arithmetic.

### M12 — CPU NTT and INTT reference engine

M12 independently generates and verifies transform parameters for `N = 16` and `N = 256` under `q = 3329`.

For an N-point NTT, a primitive root `omega` must satisfy

```
omega^N = 1 mod q
omega^(N/p) != 1 mod q for every prime divisor p of N
```

The forward transform is

```
X[k] = sum(n = 0 to N-1) x[n] * omega^(n k) mod q
```

and the inverse is

```
x[n] = N^(-1) * sum(k = 0 to N-1) X[k] * omega^(-n k) mod q
```

where `N^(-1)` is the multiplicative inverse of `N` modulo `q`.

Validated parameter values recorded by the test are:

| N | q | Primitive N-th root `omega` | `omega^(-1)` | `N^(-1) mod q` |
|---:|---:|---:|---:|---:|
| 16 | 3329 | 2699 | 1897 | 3121 |
| 256 | 3329 | 3061 | 2298 | 3316 |

The reference test checks roots, impulse and constant vectors, direct-transform agreement for random vectors, and exact NTT/INTT round trips.

### M13 — Batched 16-point NPU NTT

M13 performs 64 independent transforms of length 16, for 1024 total coefficients. It validates the NPU transform against M12's CPU reference, including impulse, constant, and random-vector behavior.

### M14 — Batched 256-point NPU NTT

M14 performs four independent 256-point transforms, also totaling 1024 coefficients. This demonstrates the larger transform configuration using the validated `N = 256`, `q = 3329`, and `omega = 3061` parameters.

### M15 — INTT and cyclic polynomial multiplication

M15 validates inverse transformation, exact NTT/INTT recovery, and cyclic convolution in

```
Z_3329[x] / (x^256 - 1)
```

For polynomials `A(x)` and `B(x)`, cyclic multiplication means terms wrap with a positive sign:

```
C[k] = sum(i + j congruent to k mod N) A[i] * B[j] mod q
```

Equivalently, after pointwise NTT-domain multiplication,

```
C = INTT(NTT(A) elementwise_multiply NTT(B))
```

provided the NTT convention, ordering, and normalization used by the implementation agree with the CPU reference.

## M16 status: negacyclic multiplication is paused

The intended M16 topic is negacyclic polynomial multiplication in

```
Z_3329[x] / (x^256 + 1)
```

For negacyclic multiplication, terms of degree at least `N` wrap with a negative sign:

```
C[k] = sum(i + j = k) A[i]B[j] - sum(i + j = k + N) A[i]B[j] mod q
```

A common twist-based construction for an ordinary N-point NTT needs a primitive `2N`-th root of unity. Here, `N = 256` would require a primitive 512-th root modulo 3329. This cannot exist because the multiplicative group order is

```
q - 1 = 3328 = 2^8 * 13
```

and `512` does not divide `3328`. The field does contain roots of order 256, but not order 512. Consequently, a full 256-point negative-wrapped NTT based on a 512-th root cannot be used under this modulus. ML-KEM/Kyber-style arithmetic instead uses an incomplete NTT and degree-2 base multiplication structure.

The experimental M16 graph also encountered an MLIR-AIE native assertion during graph construction. Therefore:

- M16 is paused.
- No M16 silicon pass is claimed.
- The direct schoolbook negacyclic equation remains the correct CPU reference.
- Future M16 work must first reproduce the working M15 MLIR-AIE host/runtime API structure, then implement a mathematically valid incomplete-NTT or other verified decomposition for `q = 3329`.

## Regression runner

`run_all_silicon_tests.py` runs the validated automated tests for M3 and M5 through M15. It intentionally does not include setup milestones M0-M2, hardware-dependent M4, or paused M16.

Run from the repository root:

```powershell
python run_all_silicon_tests.py
```

A successful regression run verifies twelve entries: M3, M5, M6, M7, M8, M9, M10, M11, M12, M13, M14, and M15.

## Numerical validation policy

- Every deterministic NPU operation requires an independent CPU reference.
- Modular arithmetic, NTTs, INTTs, and polynomial arithmetic must be bit-exact.
- `bfloat16` DSP paths must state their accepted error bound, scaling, and sample representation.
- Transform conventions, roots, input/output order, bit-reversal behavior, and normalization are part of each NTT test contract.
- A failed compile, runtime exception, assertion, or host-only result is not a silicon validation.
