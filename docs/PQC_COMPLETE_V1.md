# Post-Quantum Cryptography v1.0.0 Validation Summary

**Release tag:** `v1.0.0`

**Release date:** 2026-08-16

**Current regression boundary:** 34 invocations: 29 direct-hardware, 4 host/NPU composers, and 1 intentional CPU reference.

This document records what the repository demonstrates and, equally importantly, what it does not. It supersedes the original “33/33 silicon” wording. The detailed correction is in [`V1_0_0_VALIDATION_ERRATA.md`](V1_0_0_VALIDATION_ERRATA.md).

## FIPS 203 ML-KEM scope

The implemented end-to-end parameter set is **ML-KEM-512**. ML-KEM-768 and ML-KEM-1024 are not claimed as implemented or validated.

| Milestone | Scope | Validation boundary |
|---|---|---|
| M32b | NTT, inverse NTT, base multiplication, polynomial add/subtract over \(Z_{3329}\) | Hardware-backed against an independent host reference |
| M32c | Keccak-f[1600], SHA-3/SHAKE, SampleNTT, and SamplePolyCBD | Hardware-backed against host reference vectors |
| M32d | K-PKE component primitives | Hardware-backed; K-PKE is not presented as an approved standalone encryption scheme |
| M32e | ML-KEM-512 host/NPU composition | 60 host known-answer tests plus 9 hardware smoke vectors: 3 each for key generation, encapsulation, and decapsulation |

The M32e composer runs orchestration on the host and dispatches arithmetic and symmetric primitives through the M32b, M32c, and M32d backend seam. This is a host/NPU composition experiment, not a claim that the entire KEM executes as one fused NPU kernel.

## FIPS 204 ML-DSA scope

M33 now has checked-in, fail-closed native runners for two primitive families:

- **M33a:** NTT, inverse NTT, base multiplication, reduction, and an end-to-end polynomial multiplication gate, **420/420 PASS** with `Backend: m33a:silicon`.
- **M33b:** Power2Round, Decompose, MakeHint, UseHint, CheckNorm, and centered reduction, **700/700 PASS** with `Backend: m33b:silicon`.
- **M33d:** ML-DSA KeyGen for ML-DSA-44/65/87, **75/75 PASS** in a host/NPU composition using both native primitive backends.
- **M33e:** deterministic Sign_internal **90/90 PASS** and mixed valid/invalid Verify_internal **90/90 PASS**, again using both native primitive backends.

M33d/e are not fully device-resident ML-DSA. Python still performs SHAKE, sampling, packing, polynomial accumulation, matrix/vector orchestration, rejection-loop control, and comparison logic. The current composer does not route its SHAKE operations through M32c.

## Regression accounting

`run_all_silicon_tests.py` contains 34 invocations:

- **29 direct-hardware invocations:** DSP/SDR and primitive/component entries that dispatch their tested workload directly to the NPU, including M33a and M33b.
- **4 host/NPU composer invocations:** M32e, M33d, M33e Sign, and M33e Verify.
- **1 intentional CPU reference invocation:** M12.

The runner now assigns explicit validation policies. A generic word such as `passed` or a reference-only sentinel cannot satisfy a hardware policy. M32e must report all three hardware test groups with no skips. M33 hardware policies require explicit hardware backend declarations and reject reference/fallback declarations.

The corrected matrix completed **34/34 PASS** in **126.29 seconds** on 2026-08-17. This is a mixed-backend regression result and must not be shortened to “34 silicon workloads.”

## Reproduction

On a Phoenix/Hawk Point XDNA1 system with the pinned Windows toolchain:

```powershell
py .\install.py
py .\run_all_silicon_tests.py
```

For the ML-KEM-512 test directly:

```powershell
& .\third_party\mlir-aie\ironenv\Scripts\python.exe -m pytest `
  .\tests\m32_mlkem\test_mlkem_m32e.py -v
```

Expected M32e scope is 60 host KATs and 9 hardware smoke vectors. Do not report ML-KEM-768/1024 coverage or fully device-resident ML-DSA from this repository state.

## Claim-safe summary

Phoenix SDR-DSP contains hardware-backed DSP/SDR kernels, hardware-backed FIPS 203 building blocks, and native FIPS 204 M33a/M33b primitive gates on a consumer AMD Phoenix XDNA1 NPU. Its ML-KEM-512 and ML-DSA KeyGen/Sign/Verify paths are host/NPU composition experiments, not fused or fully device-resident implementations.

The project does not claim cryptographic certification, production hardening, constant-time behavior, or a CPU/GPU performance advantage.

## Primary references

- NIST FIPS 203, Module-Lattice-Based Key-Encapsulation Mechanism Standard: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 204, Module-Lattice-Based Digital Signature Standard: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
- NIST FIPS 202, SHA-3 Standard: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
- NIST ACVP-Server vectors: https://github.com/usnistgov/ACVP-Server
- MLIR-AIE / IRON: https://github.com/Xilinx/mlir-aie
