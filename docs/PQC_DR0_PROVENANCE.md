# PQC DR0 provenance and adaptation record

## Scope

This record covers the new DR0 package, its source-level adaptation, and the
provenance of its fused-graph validation boundary. The dedicated physical record
[`PQC_DR0_SILICON_VALIDATION_20260817.md`](PQC_DR0_SILICON_VALIDATION_20260817.md)
records the 2026-08-17 Phoenix result; it is distinct from the earlier M33a
primitive result. The historical 34-entry runner is superseded by the current
five-gate native-only canonical runner; this provenance record remains narrow
DR0 evidence.
The exact implementation baseline is repository commit
`e77e7ed2783d88b5451394866d7ddfccd9db4f69`; DR0 remains an uncommitted,
isolated addition on top of that baseline.

## Algorithm and arithmetic source

| Artifact | Exact source / revision | Relationship to DR0 |
|---|---|---|
| NIST FIPS 204 | <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>, Aug. 2024 | Defines the ML-DSA ring and arithmetic context. Consulted for the `q = 8380417`, degree-256 negacyclic-product contract. |
| pq-crystals Dilithium reference | <https://github.com/pq-crystals/dilithium/tree/master/ref>, upstream revision not independently recorded here | Existing local M33a source documents itself as a transliteration of its NTT/reduction behavior. DR0 adds no copied upstream zeta or reducer table. |
| Existing local M33a implementation | baseline commit above; original source path intentionally omitted from the production dependency graph | Used as the reviewed arithmetic antecedent. Its required constants, zeta table, defined low-32-bit Montgomery reduction, and NTT/base-multiply/INTT stages are adapted into the production-local `phoenix_sdr_dsp/pqc/kernels/m33a_arithmetic.hpp`. DR0 does not include or import any test-tree artifact. |
| Existing local M33a runner | `phoenix_sdr_dsp/silicon/m33a_runner.py`, baseline commit above | Structural precedent for lazy IRON imports, `ExternalFunction`, ObjectFIFO worker, XRT tensor usage, native-only error behavior, and a 0x4000 worker stack. DR0 does not reuse M33a's scalar control/mode ABI. |
| Existing local M33a design | `docs/M33a_DESIGN.md`, baseline commit above | Establishes the Montgomery-factor convention that DR0 cancels wholly on-device. |

The production-local `m33a_arithmetic.hpp` carries the required M33a constants,
256-entry zeta table, defined low-32-bit Montgomery reduction, forward NTT,
pointwise base multiplication, inverse NTT, and reduction helper. It is a
reviewed production adaptation, not a relative include of the prior source.
`m33_product_graph.cc` includes only this neighboring production header, allocates
local work arrays, calls the production-local transform/base-multiply/inverse
functions, and canonicalizes the final residue before terminal egress. No
production source includes or imports a test-tree artifact at compile time or
runtime.

## Runtime and topology source

| Artifact | Exact source / revision | Relationship to DR0 |
|---|---|---|
| MLIR-AIE / IRON documentation | <https://xilinx.github.io/mlir-aie/1.4.1/>, 1.4.1 | API reference for `ObjectFifo`, `Worker`, `Runtime`, `Program`, and `ExternalFunction`. No external source code copied. |
| Xilinx MLIR-AIE repository | <https://github.com/Xilinx/mlir-aie>, project pin referenced locally as `3ca0193` | Toolchain provenance only; IRON resolves the graph and routing. Pin/version must be revalidated on physical execution. |
| Xilinx Runtime | <https://github.com/Xilinx/XRT> | Provenance for the XRT tensor runtime dependency. No runtime source copied. |
| LLVM-AIE / Peano | <https://github.com/Xilinx/llvm-aie> | Compiler provenance for the AIE2 C++ source. No toolchain source copied. |
| Local M32/M33 topology patterns | baseline M32 graph and `phoenix_sdr_dsp/silicon/m33a_runner.py` | Demonstrate why Phoenix has a two-input limit and how scalar-mode M33a packs control plus operand. DR0 has exactly two genuine polynomial inputs and therefore sends them un-packed over those two channels. This is provenance only, not a production dependency. |

## Independent oracle provenance

`phoenix_sdr_dsp.pqc.abi.reference_negacyclic_product` is newly written
repository-local code. It implements ordinary direct convolution with sign flip
for terms of degree at least 256 and a final `% q`; it does not import
`dilithium-py`, the existing M33a test transliteration, or the M33a kernel. It
is an independent terminal-product oracle only, not a native fallback.

## Claims not inherited

The 420/420 M33a record in
[`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md) applies
to the prior primitive gate, not this fused graph. The dedicated DR0 record
establishes the separate `m33-dr0:silicon` 24/24 fused-product result, but does
does not inherit a complete ML-DSA/FIPS 204 claim, performance result, constant-time
claim, zeroization claim, or CMVP validation. Those limits are explicit in
[`PQC_DR0_SILICON_VALIDATION_20260817.md`](PQC_DR0_SILICON_VALIDATION_20260817.md).

## Reproduction and audit boundary

The native proof is reproducible only on a Windows Phoenix/XDNA1 laptop with the
repository's pinned IRON 1.4.1 environment, XRT-visible NPU, and Peano toolchain:

```powershell
.\third_party\mlir-aie\ironenv\Scripts\activate.bat
python tests\pqc_device_resident\test_m33_product_dr0.py
```

For audit, the dedicated validation record identifies the captured terminal log,
its SHA-256 digest, byte size, timestamp, exact command, and backend/result.
Preserve toolchain version output, compiled-artifact location/checksum if
produced, device identity, and exact working-tree diff for future reruns. A
Python reference result, a static topology test, an import failure, or a label
that says `unavailable` is expressly not evidence of physical execution.
