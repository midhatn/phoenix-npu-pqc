# v1.0.0 Validation Errata

**Published:** 2026-08-17
**Applies to:** Phoenix SDR-DSP v1.0.0 documentation and promotion

## Historical v1.0.0 correction

Earlier v1.0.0 text described the suite as “33/33” or “34/34” silicon validated and described the complete FIPS 203 and FIPS 204 tracks as executing on the Phoenix NPU. Inspection of the tracked tests and runner shows that this was too broad.

The accurate boundary of the original v1.0.0 tree was:

- **34 total regression invocations**
- **28 hardware-backed invocations**
- **1 intentional CPU-reference invocation:** M12
- **5 ML-DSA reference/KAT invocations:** M33a, M33b, M33d, M33e Sign, and M33e Verify

The original M33 tests contained optional native-runner imports and reference fallbacks. The referenced native M33 runner modules were not in that tree, so successful fallback results were not evidence of NPU execution.

## Post-release native M33 update

On 2026-08-17, native fail-closed M33a and M33b runners were added and validated on the Phoenix laptop. The updated 34-entry matrix completed **34/34 PASS** in **126.29 seconds**:

- **29 direct-hardware invocations**
- **4 host/NPU composer invocations:** M32e, M33d, M33e Sign, and M33e Verify
- **1 intentional CPU-reference invocation:** M12

M33a passed 420/420 and M33b passed 700/700 with explicit silicon backend labels. M33d passed 75/75, M33e Sign passed 90/90, and M33e Verify passed 90/90 using both native primitive backends. See [`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md).

## PQC scope

- **M32b/M32c/M32d:** hardware-backed FIPS 203 primitives and components.
- **M32e:** ML-KEM-512 only, with 60 host known-answer tests and 9 hardware smoke vectors.
- **ML-KEM-768 and ML-KEM-1024:** not implemented or validated by the current M32e test selection.
- **M33a/M33b:** native silicon primitive execution.
- **M33d/M33e:** host/NPU composition using M33a/M33b; SHAKE, sampling, packing, accumulation, and control remain host-side.

## OFDM terminology

M27 implements LS pilot estimation, linear interpolation of the channel estimate, and one-tap zero-forcing equalization. It does not implement LMMSE equalization.

## Regression behavior

The master runner now distinguishes hardware, reference, M32e hardware-smoke, and M33 hardware-backend policies. Reference-only success markers no longer satisfy a hardware policy. Missing or fallback M33 backends must fail a strict hardware run rather than being counted as silicon success.

## Claim policy

Use this wording for the post-release development tree:

> Phoenix SDR-DSP is a Windows-native AIE2/XDNA1 engineering corpus with hardware-backed DSP/SDR kernels, FIPS 203 building blocks, and native FIPS 204 M33a/M33b primitive gates. Its ML-KEM-512 and ML-DSA KeyGen/Sign/Verify paths are host/NPU compositions, not fully device-resident implementations.

Do not claim:

- 34 fully device-resident or all-silicon workloads
- fully device-resident ML-DSA
- ML-KEM-768 or ML-KEM-1024 implementation
- LMMSE equalization
- CPU/GPU acceleration without a controlled benchmark
- cryptographic certification, production hardening, or constant-time behavior

## Historical result retained

The documented v0.4.0 clean-clone **16/16** result remains a dated historical result for that earlier 16-entry hardware suite. It must not be reused as the current repository-wide count.
