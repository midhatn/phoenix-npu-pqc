# PQC DR0 — M33 device-resident polynomial-product graph

## Status and claim boundary

DR0 is a physically validated production-package graph for one fused ML-DSA
ring product on a Phoenix XDNA1 / AIE2 tile. On 2026-08-17, its native gate
reported `Backend: m33-dr0:silicon`, passed four directed plus 20 deterministic
random vectors, and reported `TOTAL 24/24 PASS` with exit code 0. The immutable
evidence details and exact claim boundary are recorded in
[`PQC_DR0_SILICON_VALIDATION_20260817.md`](PQC_DR0_SILICON_VALIDATION_20260817.md).

The following historical runner statement is superseded. DR0 is now the first
gate in the native-only `run_all_silicon_tests.py` sequence. The earlier
34-entry runner and its published 34/34 accounting are historical only, and
must not be extended by this work. Host-only checks continue to verify source
shape, ABI validation, and an independent mathematical oracle; they are
supplementary to, not a substitute for, the recorded Phoenix result.
`unavailable` remains an honest non-success state and never a fallback result.

## Operation and arithmetic contract

DR0 computes one negacyclic product in
`R_q = Z_q[x] / (x^256 + 1)` for the ML-DSA constants:

- `n = 256`
- `q = 8,380,417`
- input coefficients: ordinary Python `int`, each in `[-8,380,416, 8,380,416]`
- terminal coefficients: canonical ordinary integers in `[0, 8,380,416]`

The resident operation is:

```text
c = canonicalize(INTT(BASEMUL(NTT(a), NTT(b))))
```

`NTT`, `BASEMUL`, and `INTT` call the exact arithmetic functions in
`phoenix_sdr_dsp/pqc/kernels/m33a_arithmetic.hpp`, the production-local M33a
adaptation that carries the Montgomery zeta table and defined reducer. It has
no compile-time or runtime dependency on the repository test tree. M33a
semantics are deliberate: NTT is plain modular, base multiplication adds
`R^-1`, and INTT adds `R`; the two factors
cancel before the terminal device-side canonicalization. DR0 therefore exposes
neither NTT residues nor a Montgomery-rescaled polynomial, and callers must
not apply a host-side Montgomery repair.

The off-device oracle in `phoenix_sdr_dsp.pqc.abi.reference_negacyclic_product`
uses direct O(n²) signed wraparound convolution, not an NTT, zeta table, or
M33a reducer. It is suitable for bit-exact terminal-product comparison.

## Host ABI

| Field | Count / type | Bytes | Direction | Contract |
|---|---:|---:|---|---|
| `a` | 256 × `int32` | 1,024 | ingress 1 | plain ML-DSA polynomial |
| `b` | 256 × `int32` | 1,024 | ingress 2 | plain ML-DSA polynomial |
| `c` | 256 × `int32` | 1,024 | terminal egress | canonical product only |

The public call is `run_m33_product(a, b)`. It has no mode selector, optional
operand, control buffer, or result tuple. `validate_polynomial` performs length,
exact Python-integer type, and coefficient-range checks before IRON/XRT imports,
tensor construction, or device work. Floats, booleans, NumPy scalar objects,
strings, byte buffers, wrong lengths, and out-of-envelope values fail locally.

The host creates the terminal output tensor with the explicit sentinel
`INT32_MIN`. After the one terminal drain, every lane must have changed and be
canonical; otherwise the native call raises rather than returning a partial
buffer.

## ObjectFIFO topology and transfer invariant

```text
host a --fill--> ObjectFIFO m33_dr0_in_a --\
                                                  AIE worker --> ObjectFIFO m33_dr0_out_c --drain--> host c
host b --fill--> ObjectFIFO m33_dr0_in_b --/
```

The `Runtime.sequence` contains exactly these three transfer operations:

1. `a_prod.fill(a_in)`
2. `b_prod.fill(b_in)`
3. `c_cons.drain(c_out, wait=True)`

The worker acquires one token from each ingress FIFO and one egress token,
runs all three arithmetic stages from local arrays, and releases them. No NTT
domain, base-product, mode, or control buffer is made host-visible. `c_t.to("cpu")`
is the single terminal retrieval after the invocation; there is no intermediate
`.to("cpu")` and no `.to("cpu")` on `a` or `b`.

Phoenix permits only two input DMA channels per core tile. DR0 consumes exactly
those two channels with the real operand polynomials, so unlike scalar-mode
M33a it does not need a packed mode-plus-operand input. It has one output DMA
channel. The graph's only allowed topology is consequently **2 ingress + 1
terminal egress**.

## Modes and implementation layout

DR0 is intentionally a fixed-function mode, not an exposed multiplexed kernel:

| Layer | Entry / mode | Responsibility |
|---|---|---|
| Public package | `run_m33_product(a, b)` | strict ABI validation; native-only dispatch |
| IRON program | `m33_dr0_program` | two `ObjectFifo` inputs and one terminal output |
| AIE entry | `m33_product_graph` | M33a NTT(a), NTT(b), basemul, INTT, canonicalize |
| Production-local arithmetic | M33a `ntt_kernel`, `basemul_kernel`, `invntt_kernel` | reviewed M33a transform and Montgomery behavior; no test-tree dependency |

Temporary local arrays `a_ntt`, `b_ntt`, and `product_ntt` are 3 × 256 × 4 =
3,072 bytes. This is below the documented 64 KiB AIE2 tile-local-memory budget,
but toolchain compilation is the authoritative placement check. The 0x4000
worker stack follows the already validated M33a runner pattern; it must be
rechecked by `aiecc` on the physical toolchain.

The graph assumes the pinned MLIR-AIE / IRON 1.4.1 sequence-function API,
Phoenix NPU1 device discovery through XRT, the Peano AIE2 compiler, and the
production-local `m33a_arithmetic.hpp` file shipped beside the DR0 kernel. It
does not rely on source paths into the repository test tree. It assumes no
dynamic routing, multi-tile placement,
external lock, or runtime reconfiguration; IRON resolves the one-worker routing
when the program is compiled.

IRON 1.4.1 inspects the runtime callback annotations directly. The runner must
therefore not enable postponed annotation evaluation with
`from __future__ import annotations`; doing so turns `In` and `Out` into strings
and causes IRON to call the graph generator without its three runtime buffers.

## Failure behavior and security limitations

`BACKEND_LABEL` is exactly `m33-dr0:silicon`. If MLIR-AIE, XRT, compilation,
NPU discovery, dispatch, terminal drain, sentinel overwrite, or canonical-output
validation fails, DR0 raises `NativeBackendUnavailable`. It never calls the
reference implementation to create a success result. The physical runner prints
`Backend: m33-dr0:unavailable (...)` and exits 2 when the native path cannot be
used.

The recorded Phoenix result validates only the fused M33 negacyclic
polynomial-product graph and its 24 checked vectors. DR0 is **not** a complete
ML-DSA or FIPS 204 implementation, and this result does not establish
performance, latency, throughput, constant-time behavior, side-channel
resistance, fault resistance, zeroization, key-management, CMVP validation, or
any other production certification claim. In particular:

- The host input tensors and Python values are not zeroized.
- AIE local arrays, ObjectFIFO storage, XRT buffers, compiled artifacts, and
  runtime-managed DMA memory have no verified zeroization protocol here.
- Inputs may be public test polynomials or secrets depending on the caller;
  callers must not infer secure key handling from device residency.

## Physical validation

On a Windows Phoenix laptop after the repository's pinned installer and
`ironenv` setup, run from repository root:

```powershell
.\third_party\mlir-aie\ironenv\Scripts\activate.bat
python -m unittest tests.pqc_device_resident.test_m33_product_dr0
python tests\pqc_device_resident\test_m33_product_dr0.py
```

The first command executes host-only/static checks as well as the module tests.
The second is the native gate. The recorded 2026-08-17 Phoenix run reported the
native backend label and anchored `TOTAL 24/24 PASS`; an `unavailable` report
is not a pass. The historical instruction not to add DR0 to the runner is
superseded: the current native-only canonical sequence dispatches it first. See
[`PQC_DR0_SILICON_VALIDATION_20260817.md`](PQC_DR0_SILICON_VALIDATION_20260817.md)
for the recorded evidence.

## References

- NIST, *FIPS 204: Module-Lattice-Based Digital Signature Standard* (Aug. 2024): <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- pq-crystals Dilithium reference implementation, including `ref/ntt.c`: <https://github.com/pq-crystals/dilithium/tree/master/ref>
- MLIR-AIE 1.4.1 IRON documentation: <https://xilinx.github.io/mlir-aie/1.4.1/>
- Existing local M33a design and validation boundary: [`M33a_DESIGN.md`](M33a_DESIGN.md), [`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md)
