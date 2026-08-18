# Phoenix NPU PQC device-residency research roadmap

**Status date:** 2026-08-18

**Repository:** `phoenix-npu-pqc`

**Purpose:** claim-safe sequencing toward a long-term fully device-resident
PQC target. This roadmap is not a hardware-run authorization.

## Governing completion rule

The long-term target is **100% NPU-resident execution** for the required FIPS
202 SHA-3/SHAKE work, all supported FIPS 203 ML-KEM operations, and all
supported FIPS 204 ML-DSA operations. A completed operation has no host
cryptographic fallback, host-computed intermediate, or host repair of device
results; it has an independent oracle, fail-closed behavior, reproducible
build/provenance, and a separately recorded physical exact-output gate.

## Research-decision sequence

| Decision record | Scope | Recorded state | Boundary before advancing |
| --- | --- | --- | --- |
| **DR0** | One fused ML-DSA ring-product primitive on one AIE2 worker. | Narrow physical result retained from `7b38973`. | No complete ML-DSA or FIPS 204 residency claim follows. |
| **DR1** | ML-DSA-44 ExpandA / rejection-sampling / NTT with bounded device/host ABI. | Narrow physical result retained from `7b38973`. | No complete ML-DSA or FIPS 204 residency claim follows. |
| **DR2a** | ML-KEM-512 `SampleNTT(SHAKE128(rho || j || i))` for one matrix polynomial. | Narrow physical pass record retained. | Not K-PKE KeyGen. |
| **DR2b** | ML-KEM-512 CBD3/NTT seed-noise building block. | Narrow physical pass record retained. | Not integrated KeyGen. |
| **DR2c** | One terminal ML-KEM-512 K-PKE.KeyGen `t_hat` row. | Narrow physical pass record retained. | `G(d || k)`, both rows, serialization, and lifecycle handling remain outside the result. |
| **DR2d** | Integrated five-worker ML-KEM-512 K-PKE.KeyGen candidate. | **Physical fail: `TOTAL 0/25 FAIL`, exit 1.** | Expert resolution, a clean independently checked corpus, retained provenance, and explicit approval are required. |
| **Integrated DR2** | First integrated ML-KEM KeyGen research gate. | **Blocked.** | DR2d closure is required. |
| **DR3+** | Future research records. | **Not started.** | Integrated DR2 closure and a new reviewable scope decision. |

## Current stop state

1. The M32/M33 historical baseline is hybrid; it is not a complete residency result.
2. DR0 and DR1 are narrow physical records, not complete ML-DSA.
3. DR2a, DR2b, and DR2c are narrow physical records, not integrated ML-KEM KeyGen.
4. DR2d is an integrated physical failure, not a partial pass. It blocks DR2.
5. The protected DR2 material is retained in
   [`pqc_dr2_evidence_20260818/`](pqc_dr2_evidence_20260818/README.md).
   It is evidence and does not authorize hardware execution.

## Claim boundaries

This roadmap does not claim complete ML-KEM, complete ML-DSA, FIPS
conformance, constant-time behavior, secure zeroization, side-channel
resistance, performance, CMVP validation, certification, or production
readiness.

## References

- [FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
