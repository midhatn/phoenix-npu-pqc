# Research Ledger: FIX-DR2D-FUNCTIONAL-MISMATCH

This ledger documents the research sources, standards citations, toolchain defect analysis, and source-to-artifact manifest for the resolution of the 25/25 DR2d ML-KEM-512 K-PKE KeyGen functional mismatch.

---

## Normative Standards & Specifications

1. **NIST FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard**
   - **Issuing Organization**: National Institute of Standards and Technology (NIST), U.S. Department of Commerce.
   - **Date**: August 2024.
   - **Official URL**: https://doi.org/10.6028/NIST.FIPS.203
   - **Relevant Sections**:
     - Section 5.1, Algorithm 13 (`K-PKE.KeyGen(d)`), lines 1-7:
       - $G(d \parallel 2) \to (\rho, \sigma)$
       - $\mathbf{A} \sim \text{SampleNTT}(\text{XOF}(\rho, j, i))$
       - $\mathbf{s} \sim \text{SamplePolyCBD}_{\eta_1}(\text{PRF}(\sigma, N))$
       - $\mathbf{e} \sim \text{SamplePolyCBD}_{\eta_1}(\text{PRF}(\sigma, N))$
       - $\hat{\mathbf{t}} = \hat{\mathbf{A}} \circ \hat{\mathbf{s}} + \hat{\mathbf{e}}$
       - $ek_{pke} = \text{ByteEncode}_{12}(\hat{\mathbf{t}}) \parallel \rho$ (800 bytes for $k=2$)
       - $dk_{pke} = \text{ByteEncode}_{12}(\hat{\mathbf{s}})$ (768 bytes for $k=2$)
     - Section 4, Parameter Sets: $q = 3329$, $n = 256$, $k = 2$, $\eta_1 = 3$, $\eta_2 = 2$.
   - **Verification**: Verified bit-exact complete buffer agreement against the official NIST ACVP ML-KEM-512 K-PKE KeyGen vectors (`m32_mlkem_kpke_keygen_test_vectors.json`).

---

## Toolchain Defect & Compiler Analysis

1. **Xilinx/llvm-aie Upstream Issue #1012**:
   - **Title**: `[AIE2] Partial-word store scheduled into zero-overhead-loop end bundle is dropped on hardware`
   - **URL**: https://github.com/Xilinx/llvm-aie/issues/1012
   - **Description**: Issue #1012 reports dropped AIE2 partial-word stores associated with zero-overhead-loop scheduling.

2. **Xilinx/llvm-aie Upstream Pull Request #1221**:
   - **Title**: `Fix missed resource conflict in single-stage pipeline.`
   - **URL**: https://github.com/Xilinx/llvm-aie/pull/1221
   - **Description**: PR #1221 is the upstream fix associated with issue #1012.

3. **Installed Compiler Revision**:
   - **Git Commit**: `c9c5ecb725fc8c765e4b687356e6ec1e54da7a0e`
   - **URL**: https://github.com/Xilinx/llvm-aie/commit/c9c5ecb725fc8c765e4b687356e6ec1e54da7a0e
   - **Relationship to Fix**: Installed revision `c9c5ecb725fc8c765e4b687356e6ec1e54da7a0e` predates the merge of PR #1221.
   - **Local Observation**: The DR2d behavior is locally consistent with that reported defect. Specifically, placing `#pragma clang loop unroll(disable)` on the 32-iteration byte copy loop `for (uint32_t i = 0; i < 32; ++i) { rho[i] = state[i]; sigma[i] = state[32 + i]; }` forced generation of a hardware loop whose sub-word `st.s8` instructions dropped writes into `sigma[0..30]`. Removing the disable-unroll pragma unrolls the loop into scalar stores, preserving all 32 bytes of `sigma`.
   - **Provenance Boundary**: Repository testing does not independently prove every internal compiler mechanism described in the upstream issue; it proves that removing the disable-unroll pragma resolves the store corruption and produces bit-exact execution under the installed toolchain version.

---

## Ablation Findings & Minimal Proven Correction

Systematic ablation testing was performed across 6 distinct configurations:

- **Config 0 (Failing Baseline)**: Barrett `mod_mul`, `DR2D_DISABLE_UNROLL` on both loops $\rightarrow$ **0/25 matching** (Worker 0 `sigma` corrupted with 31 zero bytes).
- **Config 1 (Change A only)**: Canonical `(a * b) % kQ`, `DR2D_DISABLE_UNROLL` on both loops $\rightarrow$ **0/25 matching** (corrupted before NTT).
- **Config 2 (Change C only: Remove unroll pragma on output loop)**: Barrett `mod_mul`, unrolled output copy $\rightarrow$ **25/25 matching** (0 failures).
- **Config 3 (Change A + C)**: Canonical `mod_mul` + unrolled output copy $\rightarrow$ **25/25 matching** (0 failures).
- **Config 4 (Change A + B + C)**: Canonical `mod_mul` + unrolled in/out loops $\rightarrow$ **25/25 matching** (0 failures).
- **Config 5 (Change A + B + C + D)**: Canonical `mod_mul` + unrolled in/out + `alignas` $\rightarrow$ **25/25 matching** (0 failures).

**Conclusion**: Only **Change C** is necessary to resolve the functional mismatch. All other modifications (A, B, D) were reverted to preserve minimal patch scope.

---

## Source-to-Artifact Manifest

- **Build Start**: `2026-08-31T15:06:12Z`
- **Build End**: `2026-08-31T15:06:31Z`
- **Compilation Mode**: Fresh compilation from scratch (`~/.npu/cache` wiped prior to invocation).
- **Cache Directory**: `~/.npu/cache/4c1202cd83a7b21304130999`
- **Toolchain**:
  - Python: `3.13.15`
  - Peano: `llvm-aie 21.0.0 (commit c9c5ecb7)`
  - IRON: `1.4.1`

### A. COMMITTED_GIT_BLOB (Normalized Repository Objects)
*Computed directly from Git repository objects (LF line endings):*

| Source Path | Blob Size (Bytes) | SHA-256 Digest |
| :--- | :---: | :--- |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_internal.hpp` | 13,760 | `3e3feb53b1acd6a4779a0f7cfa2760245c6404d3087e138f62b58c51b4843c46` |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_seed.cc` | 3,640 | `c56d6a429819ab2abbcfde0bed71e3a43eaa6166a944997f57cf35d5a2ff234c` |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_row0_expand.cc` | 2,032 | `d95106c0f01a1a99aee21cef3fab704b1e57bd6d1d4e066f7e421f0dd0b53986` |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_row0_accumulate.cc` | 2,359 | `a577360c6e24296576daedfdc537d04765aaebfdc74eeadd34358437986e0622` |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_row1_expand.cc` | 1,985 | `c893d0158f85a00c6dfd6a7f20c6aa2c5259d397ac64c32d4c3f9e8cb82c13c8` |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_row1_accumulate.cc` | 2,451 | `235c69d008e7db656c26053a404980b7de139156c8c4671ac94a04c7fb1c9806` |
| `phoenix_sdr_dsp/pqc/kernels/dr2d_mlkem512_kpke_keygen_serialize.cc` | 4,318 | `23f691bc40410f7bdf9573a14bc01c590a3e9d2a36b07e807e415b033d49780c` |

### B. COMPILED_WORKTREE_INPUT (On-Disk Input to Toolchain)
*Exact bytes consumed by the Peano compiler on Windows (CRLF line endings on modified worktree files):*

| Source Path | Worktree Size (Bytes) | SHA-256 Digest | Line Endings |
| :--- | :---: | :--- | :---: |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_internal.hpp` | 14,028 | `e2a9165d7bd5e7a830d039a64ea04b2c28117b85266268c2c19af3b5dcd7d2c8` | CRLF |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_seed.cc` | 3,737 | `019ebc0664f7b558307911327304b196d4b8038cbc828b999519f59edc411b89` | CRLF |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row0_expand.cc` | 2,032 | `d95106c0f01a1a99aee21cef3fab704b1e57bd6d1d4e066f7e421f0dd0b53986` | LF |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row0_accumulate.cc` | 2,359 | `a577360c6e24296576daedfdc537d04765aaebfdc74eeadd34358437986e0622` | LF |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row1_expand.cc` | 1,985 | `c893d0158f85a00c6dfd6a7f20c6aa2c5259d397ac64c32d4c3f9e8cb82c13c8` | LF |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_row1_accumulate.cc` | 2,451 | `235c69d008e7db656c26053a404980b7de139156c8c4671ac94a04c7fb1c9806` | LF |
| `phoenix_sdr_dsp\pqc\kernels\dr2d_mlkem512_kpke_keygen_serialize.cc` | 4,318 | `23f691bc40410f7bdf9573a14bc01c590a3e9d2a36b07e807e415b033d49780c` | LF |

*Note on Hash Distinction*: The difference between `COMMITTED_GIT_BLOB` and `COMPILED_WORKTREE_INPUT` for the header/kernel files is solely due to CRLF line endings in the Windows working tree versus normalized LF line endings in the Git object database.

### C. Key Generated Artifacts
| Artifact Path | Size (Bytes) | SHA-256 Digest |
| :--- | :---: | :--- |
| `dr2d_kpke_keygen_seed_noise.o` | 13,780 | `0f01cac213970ef13d7ca3fa31f0daa2a660769a2a90d3f389f5ec2f3800e2cd` |
| `dr2d_kpke_keygen_row0_accumulate.o` | 8,584 | `bd0e62f4edda37ad05430672370b3c9db617a3398dddb688d8905e64ab85a159` |
| `dr2d_kpke_keygen_row0_expand.o` | 9,968 | `44fbe546b4d2e7681c6c6ea9e9191fdfd2551b1746241c0cad189d9841a8e6c2` |
| `dr2d_kpke_keygen_row1_accumulate.o` | 8,584 | `099f06578707f2518adc2d80bb515941b8bba4d49fe194819f438ee4462095e1` |
| `dr2d_kpke_keygen_row1_expand.o` | 10,000 | `45d931b10c51d1656e100e38a6f75b1eccb9b3e3289db9523ce68c23716be2ee` |
| `dr2d_kpke_keygen_serialize.o` | 6,692 | `350ffd9d5196138a08df38a2f999b82e7c69961cad16c36768955f1bfc8c7618` |
| `aie.mlir` | 9,476 | `80654869a3e74ac7bbbce65f9b5530709cc003afe4385f456e0acf0eb00324f2` |
| `final.xclbin` | 53,144 | `800939344d41a2d639bd0b777520255457957c745444fb78cfb814808036a929` |
| `insts.bin` | 420 | `16658291267b589e53860d86bfdf881a907b4e5e8c555ab89d99a6111dfccd6d` |
| `main.pdi` | 46,688 | `32a7f45ff1d11d8202d78e5c5d320969d8812e7b40c1aa5a02963f9574391576` |

---

## Evidence & Provenance Classification

- **Functional Evaluation**: Observed through the configured AIE2 target runtime. The child result matched the independent host reference oracle bit-exactly for all 25 official ACVP vectors and 10 deterministic non-ACVP regression inputs generated at runtime.
- **Execution Provenance**: Execution provenance remains `SELF_REPORTED_UNVERIFIED`.
- **Physical Provenance**: Physical provenance remains `PHYSICAL_VERIFICATION_BLOCKED` while `PHYSICAL-DISPATCH-CORROBORATION` is open.
