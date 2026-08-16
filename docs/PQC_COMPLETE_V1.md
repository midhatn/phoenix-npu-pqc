# Post-Quantum Cryptography — v1.0.0 Release Summary

**Release tag:** `v1.0.0`
**Release date:** 2026-08-16
**Silicon contract:** **33 / 33 PASS** on Phoenix NPU1 (AMD Ryzen AI, XDNA1 / AIE2)
**Track headline:** FIPS 203 ML-KEM and FIPS 204 ML-DSA both silicon-validated against NIST ACVP-Server response vectors.

This document summarizes the v1.0.0 release that closes the Post-Quantum Cryptography (PQC) track on top of the shipped SDR / DSP kernels. It should be read alongside [`ROADMAP.md`](ROADMAP.md), [`MILESTONES_AND_MATHEMATICS.md`](MILESTONES_AND_MATHEMATICS.md), and the per-sub-milestone design notes.

## 1. Contract path

The 33-entry regression contract is closed in the following order (each entry runs on Phoenix NPU1 in `run_all_silicon_tests.py`):

| # | Milestone | Focus | Status |
|---:|---|---|---|
| 1 | M3 | SAXPY | PASS |
| 2 | M5 | 8-tap FIR | PASS |
| 3 | M6 | Complex mixer / NCO | PASS |
| 4 | M7 | Power / RSSI detector | PASS |
| 5 | M8 | Fused DSP demodulator | PASS |
| 6 | M9 | 4-column parallel FIR | PASS |
| 7 | M9b | 4-column multi-stage pipeline | PASS |
| 8 | M10 | Modular arithmetic + Barrett reduction | PASS |
| 9 | M11 | Radix-2 NTT butterfly | PASS |
| 10 | M12 | CPU NTT/INTT reference | PASS |
| 11 | M13 | Batched 16-point NPU NTT | PASS |
| 12 | M14 | Batched 256-point NPU NTT | PASS |
| 13 | M15 | INTT + cyclic polynomial multiplication | PASS |
| 14 | M15b | Negacyclic polynomial multiplication ([FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ring) | PASS |
| 15 | M17 | 64-point NPU radix-4 [Stockham](https://dl.acm.org/doi/10.1145/1464182.1464209) FFT + IFFT | PASS |
| 16 | M17p | 4-column parallel FFT channelizer | PASS |
| 17 | M19 | 8-tap complex FIR | PASS |
| 18 | M20 | Fused polyphase decimator (M=4) + interpolator (L=4) | PASS |
| 19 | M21 | Fused digital down-converter (DDC) | PASS |
| 20 | M22 | Fused digital up-converter (DUC) | PASS |
| 21 | M23 | Fused polyphase channelizer (M-path) | PASS |
| 22 | M24 | Fused [Barker-13](https://en.wikipedia.org/wiki/Barker_code) matched-filter correlator | PASS |
| 23 | M25 | Fused BPSK / QPSK receiver | PASS |
| 24 | M26 | Fused QAM-16 receiver with soft-decision demapping | PASS |
| 25 | M27 | Fused OFDM loopback (FFT + CP + pilots + channel est + one-tap equalizer) | PASS |
| 26 | M32b | Post-Quantum Cryptography — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM NTT | PASS |
| 27 | M32c | Post-Quantum Cryptography — [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) Keccak-f[1600] + SHA-3 / SHAKE + samplers | PASS |
| 28 | M32d | Post-Quantum Cryptography — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) K-PKE component | PASS |
| 29 | M32e | Post-Quantum Cryptography — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM.KeyGen / Encaps / Decaps composer | PASS |
| 30 | M33a | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA NTT | PASS |
| 31 | M33b | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) rounding & hint | PASS |
| 32 | M33d | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA.KeyGen composer | PASS |
| 33 | M33e | Post-Quantum Cryptography — [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA.Sign_internal + Verify_internal composer | PASS |

M33e is a single milestone slot but covers both Sign_internal (Algorithm 7) and Verify_internal (Algorithm 8); the underlying regression runner reports them as two entries counted together in the 33-headline. M33c has no dedicated silicon slot: FIPS 204 shares the [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) Keccak-f[1600] permutation with FIPS 203, so the M32c SHAKE kernel is reused unchanged per [FIPS 204 §3.3.5](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf).

## 2. FIPS 203 ML-KEM (M32)

[FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) *Module-Lattice-Based Key-Encapsulation Mechanism Standard* was published 2024-08-13 ([DOI 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203)). ML-KEM is derived from round-3 [CRYSTALS-Kyber](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf) (FIPS 203 §1.1); the implementation follows FIPS 203 whenever Appendix C notes a difference.

The three approved parameter sets ([FIPS 203 Table 2](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)) share `(n, q) = (256, 3329)`:

| Set | k | η1 | η2 | du | dv |
|---|---:|---:|---:|---:|---:|
| ML-KEM-512 | 2 | 3 | 2 | 10 | 4 |
| ML-KEM-768 | 3 | 2 | 2 | 10 | 4 |
| ML-KEM-1024 | 4 | 2 | 2 | 11 | 5 |

### Sub-milestones

- **M32b — NTT-domain negacyclic product ([Algorithms 9–12](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf))** — Silicon-dispatched NTT kernel over `Z_3329` with the pq-crystals ζ-table matching [`ref/ntt.c`](https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c). Kernel: `tests/m32_mlkem/ntt_kernel.cc`. Design: [`M32b_DESIGN.md`](M32b_DESIGN.md).
- **M32c — Keccak-f[1600] + SHA-3 / SHAKE + samplers ([Algorithms 7–8](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf))** — Single Keccak-f[1600] permutation ([FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf)) dispatches SHAKE128 / SHAKE256 / SHA3-256 / SHA3-512 / SampleNTT / SamplePolyCBD across five modes. Kernel: `tests/m32_mlkem/keccak_shake_kernel.cc`. Design: [`M32c_DESIGN.md`](M32c_DESIGN.md).
- **M32d — K-PKE component ([Algorithms 13–15](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf))** — Silicon-dispatched K-PKE.KeyGen / Encrypt / Decrypt orchestrated on top of M32b + M32c. Kernel: `tests/m32_mlkem/kpke_kernel.cc`. Design: [`M32d_DESIGN.md`](M32d_DESIGN.md). Not approved standalone per [FIPS 203 §3.3](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf).
- **M32e — ML-KEM.KeyGen / Encaps / Decaps composer ([Algorithms 19–21](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf))** — Composer `tests/m32_mlkem/mlkem_composer.py` calls the M32b + M32c + M32d kernels through a `SiliconBackend` seam and is bit-exact against NIST ACVP-Server ML-KEM-{512, 768, 1024} keyGen and encapDecap tgIds. Design: [`M32e_DESIGN.md`](M32e_DESIGN.md).

### Reference oracle

[`kyber-py` 1.0.1](https://github.com/GiacomoPope/kyber-py) — pure-Python reference implementation. Composer output is checked byte-for-byte against this library and independently against the NIST ACVP-Server response vectors vendored under `tests/m32_mlkem/vectors/`.

## 3. FIPS 204 ML-DSA (M33)

[FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) *Module-Lattice-Based Digital Signature Standard* was published 2024-08-13 ([DOI 10.6028/NIST.FIPS.204](https://doi.org/10.6028/NIST.FIPS.204)). ML-DSA is derived from round-3 [CRYSTALS-Dilithium](https://pq-crystals.org/dilithium/data/dilithium-specification-round3-20210208.pdf); implement FIPS 204 wherever the two differ.

The three approved parameter sets ([FIPS 204 Table 1](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf)) share `(n, q) = (256, 8380417)` with `q = 2^23 - 2^13 + 1`, `q ≡ 1 mod 512`:

| Set | (k, ℓ) | η | λ | γ₁ | γ₂ | τ | β | ω |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ML-DSA-44 | (4, 4) | 2 | 128 | 2^17 | (q-1)/88 = 95232 | 39 | 78 | 80 |
| ML-DSA-65 | (6, 5) | 4 | 192 | 2^19 | (q-1)/32 = 261888 | 49 | 196 | 55 |
| ML-DSA-87 | (8, 7) | 2 | 256 | 2^19 | (q-1)/32 = 261888 | 60 | 120 | 75 |

### Sub-milestones

- **M33a — ML-DSA NTT ([Algorithms 41–45](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf))** — Silicon-dispatched NTT / INTT / basemul kernel in Montgomery form over `Z_8380417` with the pq-crystals ζ-table matching [`ref/ntt.c`](https://github.com/pq-crystals/dilithium/blob/master/ref/ntt.c). Kernel: `tests/m33_mldsa/dilithium_ntt_kernel.cc`. Design: [`M33a_DESIGN.md`](M33a_DESIGN.md). 420 / 420 gate PASS.
- **M33b — Rounding & hint ([Algorithms 30–33](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf))** — Silicon-dispatched Decompose (HighBits, LowBits), MakeHint, UseHint, CheckNorm with per-parameter-set γ₂. Kernel: `tests/m33_mldsa/dilithium_sampler_kernel.cc`. Design: [`M33b_DESIGN.md`](M33b_DESIGN.md). 700 / 700 gate PASS.
- **M33c — SHAKE / Keccak reuse** — No dedicated silicon slot; the M32c Keccak-f[1600] permutation serves both KEM and signature paths per [FIPS 204 §3.3.5](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf).
- **M33d — ML-DSA.KeyGen composer ([Algorithm 6](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf))** — Composer `tests/m33_mldsa/mldsa_composer.py` expands `A` via ExpandA, samples `s₁, s₂` via ExpandS, packs `t₁ = HighBits(t, 2·γ₂)` into the public key and `t₀ = t - t₁ · 2^d` into the secret key, and stamps `tr = SHAKE256(pk, 512 bits)`. Design: [`M33d_DESIGN.md`](M33d_DESIGN.md). 75 / 75 gate PASS against NIST ACVP-Server ML-DSA-{44, 65, 87} keyGen KATs.
- **M33e — ML-DSA.Sign_internal + Verify_internal composer ([Algorithms 7 and 8](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf))** — Implements the ExpandMask rejection loop with counter `κ`, SampleInBall, HighBits / LowBits / MakeHint / UseHint dispatch through M33b, the `‖z‖_∞`, `‖r_0‖_∞`, `‖c · t_0‖_∞`, and `popcount(h) ≤ ω` gate checks, and bit-packing of `σ = (č, z, h)`. Verify_internal re-derives `w₁' = UseHint(h, A_hat · NTT(z) - c · NTT(t₁ · 2^d))` and accepts iff `č = SHAKE256(μ ‖ w1Encode(w₁'), 2λ bits)`. Both `externalMu` paths supported. Design: [`M33e_DESIGN.md`](M33e_DESIGN.md).

### Reference oracle

[`dilithium-py` 1.4.0](https://github.com/GiacomoPope/dilithium-py) — pure-Python reference implementation. Composer output is checked byte-for-byte against this library and independently against the NIST ACVP-Server response vectors vendored under `tests/m33_mldsa/vectors/`.

### M33e final gate

- **sigGen (Algorithm 7):** 90 / 90 deterministic sign PASS across ML-DSA-44, ML-DSA-65, and ML-DSA-87 (NIST ACVP-Server sigGen tgIds 7–12; both non-externalMu and externalMu paths).
- **sigVer (Algorithm 8):** 90 / 90 PASS including 72 must-reject tampered signatures (NIST ACVP-Server sigVer tgIds 7–12; both non-externalMu and externalMu paths).
- **Combined:** **180 / 180**.

## 4. Silicon-agnostic composer seam

Both composers (`mlkem_composer.py`, `mldsa_composer.py`) call the M32b / M32c / M32d / M33a / M33b kernels through a `SiliconBackend` seam. When silicon is unavailable — for example, during CI on a machine without a Phoenix NPU — the backend falls through to a bit-exact Python transliteration of each kernel and the composer still passes end-to-end against the vendored KATs. This is the property that lets `run_all_silicon_tests.py` remain deterministic across the developer laptop, sandbox reference runs, and clean-clone re-verifies.

## 5. Reproducing the 33 / 33 result

Prerequisite: a Phoenix / Hawk Point Ryzen laptop with the AMD NPU driver, the toolchain pins from [`M2_TOOLCHAIN_PIN.md`](M2_TOOLCHAIN_PIN.md), and the PQC reference packages installed inside the `ironenv` per [`SETUP_WINDOWS.md §Post-Quantum Cryptography reference dependencies`](SETUP_WINDOWS.md#post-quantum-cryptography-reference-dependencies-m32--m33).

```powershell
conda deactivate
git clone https://github.com/midhatn/phoenix-sdr-dsp.git
cd phoenix-sdr-dsp
py .\install.py

.\third_party\mlir-aie\ironenv\Scripts\activate.bat
pip install kyber-py==1.0.1 dilithium-py==1.4.0 pycryptodome==3.20.0 pyshake==1.0.0

py .\run_all_silicon_tests.py
```

Expected outcome: **33 / 33 PASS** on Phoenix NPU1. Timings depend on xclbin cache state (see the v0.4.0 baseline in [`ROADMAP.md`](ROADMAP.md)).

## References

### NIST standards

- NIST, FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (2024-08-13). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 203 landing page. https://csrc.nist.gov/pubs/fips/203/final
- NIST, FIPS 204, *Module-Lattice-Based Digital Signature Standard* (2024-08-13). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
- NIST FIPS 204 landing page. https://csrc.nist.gov/pubs/fips/204/final
- NIST, FIPS 202, *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions* (2015). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
- NIST Post-Quantum Cryptography project. https://csrc.nist.gov/projects/post-quantum-cryptography
- NIST CAVP. https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program

### Round-3 lattice specifications

- Avanzi et al., *CRYSTALS-Kyber* Algorithm Specification v3.02 (2021-08-04). https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf
- Ducas et al., *CRYSTALS-Dilithium* Algorithm Specification v3.1 (2021-02-08). https://pq-crystals.org/dilithium/data/dilithium-specification-round3-20210208.pdf
- pq-crystals reference implementations — [kyber](https://github.com/pq-crystals/kyber) and [dilithium](https://github.com/pq-crystals/dilithium).

### Reference oracles and test vectors

- NIST ACVP-Server — [`usnistgov/ACVP-Server`](https://github.com/usnistgov/ACVP-Server). Response vectors vendored under `tests/m32_mlkem/vectors/` and `tests/m33_mldsa/vectors/`.
- G. Pope, [`kyber-py` 1.0.1](https://github.com/GiacomoPope/kyber-py) — Python reference ML-KEM implementation (M32e oracle).
- G. Pope, [`dilithium-py` 1.4.0](https://github.com/GiacomoPope/dilithium-py) — Python reference ML-DSA implementation (M33d and M33e oracle).
- Legion of the Bouncy Castle, [`pycryptodome` 3.20.0](https://www.pycryptodome.org/) — SHA-3 / SHAKE primitives.
- [`pyshake` 1.0.0](https://pypi.org/project/pyshake/) — SHAKE / cSHAKE utility.

### Hardware and toolchain

- AMD, "AMD Ryzen™ 9 7940HS" — Phoenix NPU rated up to 10 TOPS. https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html
- The Linux Kernel, "AMD NPU" — XDNA1 4×5 topology and the `amdxdna` driver. https://docs.kernel.org/accel/amdxdna/amdnpu.html
- Xilinx / AMD, MLIR-AIE. https://github.com/Xilinx/mlir-aie
- Native Windows IRON guide, mlir-aie 1.4.1. https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/
- Xilinx / AMD, llvm-aie (Peano). https://github.com/Xilinx/llvm-aie
- Xilinx / AMD, XRT. https://github.com/Xilinx/XRT

### In-repo companion documents

- [`ROADMAP.md`](ROADMAP.md) — full milestone status, references, and v1.0.0 completion block.
- [`MILESTONES_AND_MATHEMATICS.md`](MILESTONES_AND_MATHEMATICS.md) — DSP and PQC math with equations and citations.
- [`SETUP_WINDOWS.md`](SETUP_WINDOWS.md) — installation walkthrough including the PQC pip step.
- [`../requirements/toolchain-versions.md`](../requirements/toolchain-versions.md) — pinned reference-package versions.
