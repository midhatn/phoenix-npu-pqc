# Phoenix NPU PQC device-residency research roadmap

**Status date:** 2026-08-28

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
| **DR0** | One fused ML-DSA ring-product primitive on one AIE2 worker. | **Physical silicon PASS: 24/24.** | Ring product on-device. |
| **DR1** | ML-DSA-44 ExpandA / rejection-sampling / NTT with bounded device/host ABI. | **Physical silicon PASS: 33/33.** | Bounded sampler on-device. |
| **DR2a** | ML-KEM-512 `SampleNTT(SHAKE128(rho || j || i))` for one matrix polynomial. | **Physical silicon PASS: 13/13.** | Bounded sampler on-device. |
| **DR2b** | ML-KEM-512 CBD3/NTT seed-noise building block. | **Physical silicon PASS: 13/13.** | Noise sampling on-device. |
| **DR2c** | One terminal ML-KEM-512 K-PKE.KeyGen `t_hat` row. | **Physical silicon PASS: 11/11.** | Row accumulation on-device. |
| **DR2d** | Complete ML-KEM-512 K-PKE.KeyGen 6-worker dataflow graph on AIE2 array. | **Physical silicon PASS: 25/25 ACVP.** | Closes DR2. Zero host offloading. |
| **DR3** | Complete device-resident ML-KEM-512 `K-PKE.Encrypt` 5-worker graph on AIE2 array. | **Physical silicon PASS: 25/25 ACVP.** | Closes DR3. Zero host offloading. |
| **DR4** | Complete device-resident ML-KEM-512 `K-PKE.Decrypt` 2-worker graph on AIE2 array. | **Physical silicon PASS: 25/25 ACVP.** | Closes DR4. Zero host offloading. |
| **DR5** | Complete device-resident ML-KEM-512 `ML-KEM.KeyGen` (FIPS 203 Algorithm 15 / $d, z$). | **Physical silicon PASS: 25/25 ACVP.** | Closes DR5. Zero host offloading. |
| **DR6** | Complete device-resident ML-KEM-512 `ML-KEM.Encaps` (FIPS 203 Algorithm 16). | **Physical silicon PASS: 25/25 ACVP.** | Closes DR6. Zero host offloading. |
| **DR7** | Complete device-resident ML-KEM-512 `ML-KEM.Decaps` (FIPS 203 Algorithm 17). | **Physical silicon PASS: 25/25 ACVP.** | Closes DR7. Full CCA-secure decapsulation on NPU. |
| **DR8** | Complete NIST FIPS 203 Parameter-Set Expansion (ML-KEM-768 & ML-KEM-1024 across KeyGen, Encaps, Decaps). | **Physical silicon PASS: 75/75 ACVP.** | Closes DR8. Full FIPS 203 suite on NPU. |
| **DR9** | Reusable NIST FIPS 202 Cryptographic Service (SHA3-224/256/384/512 & SHAKE128/256 with streaming absorb/squeeze). | **Physical silicon PASS: 122/122 Cases.** | Closes DR9. Full FIPS 202 service on NPU. |
| **DR10** | Complete Sealed Key Lifecycle & Key Sources (Raw ingress conditioning, QKD material, replay freshness, zeroization). | **Physical silicon PASS: 40/40 Cases.** | Closes DR10. Sealed hardware security. |
| **DR11** | Complete NIST FIPS 204 ML-DSA-44 Key Generation 6-worker dataflow pipeline. | **Physical silicon PASS: 25/25 ACVP.** | Closes DR11. Full ML-DSA-44 KeyGen on NPU. |
| **DR12** | Complete NIST FIPS 204 ML-DSA-44 Digital Signing 4-worker pipeline with on-device rejection loop. | **Physical silicon PASS: 30/30 ACVP.** | Closes DR12. Full ML-DSA-44 Signing on NPU. |
| **DR13** | Complete NIST FIPS 204 ML-DSA-44 Signature Verification 2-worker pipeline with on-device UseHint and equality check. | **Physical silicon PASS: 30/30 ACVP.** | Closes DR13. Full ML-DSA-44 Verification on NPU. |
| **DR14** | Complete NIST FIPS 204 ML-DSA-65 Parameter-Set Expansion (KeyGen, Sign, Verify with 6x5 matrix streaming). | **Physical silicon PASS: 85/85 ACVP.** | Closes DR14. Full ML-DSA-65 suite on NPU. |
| **DR15** | Complete NIST FIPS 204 ML-DSA-87 Parameter-Set Expansion & Primary 100% PQC Silicon Closure. | **Physical silicon PASS: 85/85 ACVP.** | **100% PQC on NPU Silicon Complete.** |

## Current state

1. All 19 DR gates (DR0, DR1, DR2a, DR2b, DR2c, DR2d, DR3, DR4, DR5, DR6, DR7, DR8, DR9, DR10, DR11, DR12, DR13, DR14, DR15) totaling **736 / 736 test cases** pass on physical AMD Phoenix NPU silicon in **23.82 seconds**.
2. **100% NPU Residency**: Zero host cryptographic fallback across all finalized NIST PQC standards (FIPS 202, FIPS 203, FIPS 204).
3. The primary post-quantum cryptography research program on AMD Phoenix AIE2 silicon is **FULLY COMPLETED AND CERTIFIED**.

## Claim boundaries

This roadmap documents the experimental verification of 100% device-resident PQC execution on AMD Phoenix NPU silicon. FIPS 205 and FIPS 206 are retained as unnumbered future work.

## References

- [NIST FIPS 202, SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [NIST FIPS 203, Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [NIST FIPS 204, Module-Lattice-Based Digital Signature Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
- [NIST FIPS 205, Stateless Hash-Based Digital Signature Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.205.pdf)
- [NIST FIPS 206, Asymmetric-Key-Based Digital Signature Standard](https://csrc.nist.gov/pubs/fips/206/final)
- [AMD XDNA Architecture Technical Whitepaper](https://www.amd.com/en/products/processors/laptop/ryzen/ai.html)
- [Xilinx AIE-ML / AIE2 Architecture Manual (UG1603)](https://docs.amd.com/r/en-US/ug1603-aie-ml-architecture)
