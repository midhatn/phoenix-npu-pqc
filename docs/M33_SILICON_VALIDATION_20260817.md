# M33 Phoenix silicon validation — 2026-08-17

## Evidence boundary

These results were produced on the project's Windows Phoenix XDNA1 test host
from base commit `4bc0f158e9208469cf356d1349cef1aff55e8e47` plus the uncommitted
M33 native-runner corrections described in `M33_SILICON_HANDOFF_20260817.md`.
The tests used the checkout-local MLIR-AIE/IRON Python environment and
`PEANO_INSTALL_DIR` under its pinned `llvm-aie` package.

The word **silicon** below applies to the M33a and M33b primitive dispatches.
M33d/e are host-orchestrated composers: Python still performs SHAKE, sampling,
packing, polynomial accumulation, matrix/vector control, and signing-loop
control.

## Recorded commands and results

### M33a — NTT family

```powershell
& $py tests\m33_mldsa\test_dilithium_ntt_m33a.py
```

Backend: `m33a:silicon`

| Gate | Result |
|:--|--:|
| MODE_NTT | 50/50 PASS |
| MODE_INTT | 50/50 PASS |
| MODE_BASEMUL | 100/100 PASS |
| MODE_REDUCE | 200/200 PASS |
| End-to-end multiplication | 20/20 PASS |
| **Total** | **420/420 PASS** |

### M33b — rounding and hint primitives

```powershell
& $py tests\m33_mldsa\test_dilithium_sampler_m33b.py
```

Backend: `m33b:silicon`

| Gate | Result |
|:--|--:|
| MODE_POWER2ROUND | 100/100 PASS |
| MODE_DECOMPOSE, alpha 190464 | 50/50 PASS |
| MODE_DECOMPOSE, alpha 523776 | 50/50 PASS |
| MODE_MAKEHINT, alpha 190464 | 50/50 PASS |
| MODE_MAKEHINT, alpha 523776 | 50/50 PASS |
| MODE_USEHINT, alpha 190464 | 50/50 PASS |
| MODE_USEHINT, alpha 523776 | 50/50 PASS |
| MODE_CHECKNORM | 200/200 PASS |
| MODE_REDUCE_PM | 100/100 PASS |
| **Total** | **700/700 PASS** |

### M33d — ML-DSA KeyGen hybrid composer

```powershell
& $py tests\m33_mldsa\test_mldsa_keygen_m33d.py
```

Backend: `m33a:silicon, m33b:silicon`

ML-DSA-44, ML-DSA-65, and ML-DSA-87 each passed 25/25 NIST ACVP KeyGen
vectors, for **75/75 PASS**.

### M33e — ML-DSA Sign_internal hybrid composer

```powershell
& $py tests\m33_mldsa\test_mldsa_sign_m33e.py
```

Backend: `m33a:silicon, m33b:silicon`

The selected deterministic internal groups, tgIds 7-12, passed **90/90**:
15 vectors for each parameter-set/externalMu combination.

### M33e — ML-DSA Verify_internal hybrid composer

```powershell
& $py tests\m33_mldsa\test_mldsa_verify_m33e.py
```

Backend: `m33a:silicon, m33b:silicon`

The selected internal groups, tgIds 7-12, passed **90/90**, including 18
valid signatures accepted and 72 tampered signatures rejected.

## Reproducibility and provenance

The standards, ACVP vector source, reference repositories, licenses, adapted
code paths, and toolchain dependencies are recorded with URLs and
copied-versus-consulted classifications in
`docs/M33_SILICON_PROVENANCE.md`. The main sources are:

- NIST FIPS 204:
  <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- NIST ACVP-Server vectors:
  <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>
- pq-crystals Dilithium:
  <https://github.com/pq-crystals/dilithium>
- `dilithium-py`:
  <https://github.com/GiacomoPope/dilithium-py>
- MLIR-AIE/IRON:
  <https://xilinx.github.io/mlir-aie/1.4.1/>

## Complete regression result

After adding the standardized M12 CPU-reference sentinel, the strict master
runner completed:

```text
Total Tests Run: 34 | Passed: 34 | Failed: 0
Total Elapsed Time: 126.29 seconds
ALL REQUIRED HARDWARE-BACKED AND REFERENCE REGRESSION TESTS PASSED
Exit code: 0
```

Backend accounting for this run:

- 29 direct-hardware invocations.
- 4 host/NPU composer invocations: M32e, M33d, M33e Sign, and M33e Verify.
- 1 intentional CPU-reference invocation: M12.

The captured PowerShell transcript contained 1,485 lines and 105,109 bytes.
Its SHA-256 digest was:

```text
A8B76189A65E3606C91751AD1C90EF0CC67A989697A5FF579DF24E8C84509238
```

The raw transcript is validation evidence, not a required tracked source file.

## Claims supported by this record

Supported:

- M33a NTT-family primitives and M33b rounding/hint primitives compiled,
  dispatched, and matched their independent host references on Phoenix XDNA1.
- The selected ML-DSA KeyGen, deterministic Sign_internal, and Verify_internal
  ACVP vectors passed in a host-orchestrated composition using those native
  polynomial backends.

Not supported:

- Fully NPU-resident or entirely on-tile ML-DSA.
- Constant-time or production-hardened cryptography.
- CPU/GPU speedup or energy-efficiency claims.
- Full external-interface, arbitrary-context, randomized-signing, or complete
  ACVP-group coverage.
