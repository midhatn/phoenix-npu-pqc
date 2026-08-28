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
| **DR0** | One fused ML-DSA ring-product primitive on one AIE2 worker. | Physical silicon PASS: 24/24. | Ring product on-device. |
| **DR1** | ML-DSA-44 ExpandA / rejection-sampling / NTT with bounded device/host ABI. | Physical silicon PASS: 33/33. | Bounded sampler on-device. |
| **DR2a** | ML-KEM-512 `SampleNTT(SHAKE128(rho || j || i))` for one matrix polynomial. | Physical silicon PASS: 13/13. | Bounded sampler on-device. |
| **DR2b** | ML-KEM-512 CBD3/NTT seed-noise building block. | Physical silicon PASS: 13/13. | Noise sampling on-device. |
| **DR2c** | One terminal ML-KEM-512 K-PKE.KeyGen `t_hat` row. | Physical silicon PASS: 11/11. | Row accumulation on-device. |
| **DR2d** | Complete ML-KEM-512 K-PKE.KeyGen 6-worker dataflow graph on AIE2 array. | **Physical silicon PASS: 25/25 ACVP.** | Closes DR2. Zero host offloading. |
| **Integrated DR2** | First complete device-resident ML-KEM KeyGen research gate. | **CLOSED & VALIDATED (2026-08-28).** | All 25 ACVP cases passing on silicon. |
| **DR3** | Complete device-resident ML-KEM-512 `K-PKE.Encrypt`. | **Next active milestone.** | Requires full encryption corpus and physical validation. |
| **DR4–DR7** | Complete ML-KEM-512 Decrypt, KeyGen, Encaps, Decaps. | **Sequenced.** | Sequential execution without host repair. |
| **DR8–DR15** | Full FIPS 203 parameter sets (768/1024), FIPS 202 service, and FIPS 204 ML-DSA. | **Sequenced.** | Primary 100% PQC on NPU closure. |

## Current state

1. All 6 initial DR gates (DR0, DR1, DR2a, DR2b, DR2c, DR2d) totaling 119 cases pass on physical AMD Phoenix NPU silicon.
2. DR2 / DR2d is fully closed with 25/25 ACVP passes on physical hardware.
3. The next active research target is DR3 (ML-KEM-512 `K-PKE.Encrypt`).

## Claim boundaries

This roadmap does not claim complete ML-KEM, complete ML-DSA, FIPS
conformance, constant-time behavior, secure zeroization, side-channel
resistance, performance, CMVP validation, certification, or production
readiness.

## References

- [FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
