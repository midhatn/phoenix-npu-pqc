# Customer Quarantined Deliverables: Technical Autopsy & Remediation Roadmap

**Document Classification:** Customer Engineering Reference & Forensic Audit Report  
**Authoritative Scope:** Milestone Deliverables DR0 through DR42 (AMD Phoenix XDNA1 / AIE2 Architecture)  
**Governing Policies:** Kernel Integrity Policy, Zero-Speculation Directive, Autonomous Execution Constitution  
**Target Platform:** AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2, PCI ID `1502`, BDF `0066:00:01.1`)  

---

## 1. Executive Summary & Policy Authority

During the comprehensive customer-readiness forensic audit, **ten (10) late-roadmap deliverables** were identified as containing critical mathematical shortcuts, synthetic invariants, host-supplied intermediates, or sham verifications. 

Under the repository's **Kernel Integrity Policy** and **Zero-Speculation Directive**, an engineering implementation must execute genuine mathematical algorithms and must never specialize behavior to test vectors, embed fixed expected outputs, or substitute trivial heuristics for standardized cryptographic computations.

In accordance with the **Three-Strike Rule** (Constitution Section 8):
1. All 10 defective deliverables were placed into **IMMEDIATE MANDATORY QUARANTINE** (`BLOCKED_THREE_STRIKES`).
2. They are strictly excluded from the customer offline demonstration denominator.
3. The overall verdict for the un-quarantined full roadmap is **CUSTOMER READY: NO-GO**.
4. Customer demonstrations are bounded exclusively to authentic, verified on-tile core primitives: **NIST FIPS 202 (SHA-3/SHAKE)**, **NIST FIPS 203 (ML-KEM-512/768/1024)**, and **NIST FIPS 204 (ML-DSA-44/65/87)**.

This document details the exact technical defect for each quarantined deliverable, provides the exact source code locations and code snippets in the repository, maps where these findings are recorded across repository audit files, and outlines the feasibility and architecture required to remediate each deliverable across three distinct engineering categories.

---

## 2. Master Quarantined Deliverables Summary

### Active Quarantined Deliverables (6 Remaining)

| Milestone | Claimed Operation | Primary Standard | Exact File Location | Defect Mechanism | Remediation Category | Current Status |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **DR21** | NIST FIPS 205 SLH-DSA | FIPS 205 (SPHINCS+) | `phoenix_sdr_dsp/pqc/kernels/dr21_slhdsa_service.cc` | Sham hypertree check over public hash stream | **Category 3** | `BLOCKED_THREE_STRIKES` |
| **DR22** | NIST Draft FIPS 206 FN-DSA | Draft FIPS 206 (Falcon) | `phoenix_sdr_dsp/pqc/kernels/dr22_fndsa_service.cc` | Secret-free sign; 512-element buffer stack overflow | **Category 3** | `BLOCKED_THREE_STRIKES` |
| **DR36** | Formal Verification & SMT Models | SMT-LIB 2.0 / Z3 | `phoenix_sdr_dsp/pqc/dr36_formal_verification.py` | Strided sampling mislabeled as universal formal proof | **Category 2** | `BLOCKED_THREE_STRIKES` |
| **DR38** | Randomness Statistical Battery | NIST SP 800-22 / AIS 31 | `phoenix_sdr_dsp/pqc/dr38_randomness_abi.py` | Invalid frequency check claimed as Shannon entropy | **Category 2** | `BLOCKED_THREE_STRIKES` |
| **DR39** | dudect Side-Channel Timing | dudect / ISO 17825 | `phoenix_sdr_dsp/pqc/kernels/dr39_dudect_service.cc` | Hardcoded constant cycle counts (`48/48`) in accumulator | **Category 2** | `BLOCKED_THREE_STRIKES` |
| **DR41** | Quantum Key Management (Q-KMS) | ETSI GS QKD 014 | `phoenix_sdr_dsp/pqc/kernels/dr41_qkms_service.cc` | Ephemeral vault re-ingressed from host on each call | **Category 2** | `BLOCKED_THREE_STRIKES` |

### Remediated Deliverables: Category 1 Native Hardware Composition (4 Remediated)

| Milestone | Deliverable | Primary Standard | Connected Hardware Primitives | Test Execution Outcome | Remediated Status |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **DR30** | 3GPP 5G/6G Core Network SUCI | 3GPP TS 33.501 | AIE2 ML-KEM-512 Decaps (DR7) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR31** | X.509 PQ Certificates & CMS | RFC 5280 / RFC 5652 | AIE2 ML-DSA-44 Verify (DR13) + ML-KEM-512 Decaps (DR7) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR34** | TCG DICE / TPM Attestation | TCG DICE Architecture | AIE2 ML-DSA-44 Verify (DR13) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR42** | ANSSI Composite Dual-Signatures | ANSSI Guide / IETF | AIE2 ML-DSA-44 Verify (DR13) + Ed25519 | 25 matching, 0 failing (exit 0) | **REMEDIATED** |

---

## 3. Detailed Technical Autopsy by Deliverable

### 1. DR42: ANSSI Composite & Dual-Signature Engine
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_internal.hpp#L344-L351`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_internal.hpp#L344-L351)
* **The Committed Shortcut:**
  ```cpp
  // Algebraic commitment check: low parity matching
  uint32_t check = 0;
  DR42_DISABLE_UNROLL
  for (size_t i = 0; i < 32 && i < trad_sig_len; ++i) {
      uint8_t d_byte = digest[i];
      uint8_t p_byte = trad_pk[i % trad_pk_len];
      check ^= (trad_sig[i] ^ p_byte ^ d_byte);
  }
  return ((check & 0x01) == 0) ? 1 : 0;
  ```
* **Vulnerability Analysis:** Instead of implementing actual Ed25519/ECDSA point multiplication and ML-DSA verification, the verification functions execute a loop over 32 bytes and return `(check & 0x01) == 0`. Any arbitrary byte string whose lowest parity bit is zero is accepted as a cryptographically valid signature. Tampering with any byte other than the low bit preserves validity.

---

### 2. DR31: X.509 Post-Quantum Certificates & CMS Hybrid Co-Processor
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr31_x509_cms_internal.hpp#L161-L165`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr31_x509_cms_internal.hpp#L161-L165) and [`#L210-L216`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr31_x509_cms_internal.hpp#L210-L216)
* **The Committed Shortcut:**
  ```cpp
  // 1. Signature check:
  uint32_t parity = (sig_tag ^ expected_tag);
  return ((parity & 0x01) == 0) ? 1 : 0;

  // 2. Content Encryption Key (CEK) unwrapping:
  uint32_t kek[8];
  for (int i = 0; i < 8; ++i) {
      kek[i] = 0x243F6A88 ^ ((const uint32_t*)kem_ct)[i % (ct_len / 4)];
  }
  ```
* **Vulnerability Analysis:** Certificate signatures are verified via a 1-bit parity heuristic. More critically, CEK unwrapping computes the Key Encryption Key (KEK) by XORing public ciphertext bytes with the arbitrary constant `0x243F6A88`. No private key is ingested or utilized. Any eavesdropper observing the public ciphertext on the wire can instantly recover the plaintext CEK.

---

### 3. DR34: Hardware Root of Trust, TCG DICE / TPM Attestation
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr34_dice_tpm_service.cc#L102-L107`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr34_dice_tpm_service.cc#L102-L107)
* **The Committed Shortcut:**
  ```cpp
  // Verify simulated signature binding (first byte signature check)
  int sig_match = 1;
  if (sig_bytes[0] == 0xFF) {
      sig_match = 0; // Tampered signature marker
  }
  ```
* **Vulnerability Analysis:** Cryptographic attestation quote verification checks whether the first byte of the signature is `0xFF`. If byte 0 is not `0xFF`, the quote is certified as an authentic hardware attestation from the TPM/DICE root of trust. No asymmetric public key signature validation occurs.

---

### 4. DR21: NIST FIPS 205 SLH-DSA (SPHINCS+)
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr21_slhdsa_service.cc#L142-L146`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr21_slhdsa_service.cc#L142-L146)
* **The Committed Shortcut:**
  ```cpp
  // 2. Reconstruct and verify HT signature streamingly
  const uint8_t *chunks_ht[4] = {digest, fors_sig, pk_root, pk_seed};
  const uint32_t lens_ht[4] = {digest_len, fors_sig_len, n, n};
  const bool is_match = verify_stream_match(chunks_ht, lens_ht, 4, ht_sig, ht_sig_len);
  ```
* **Vulnerability Analysis:** The hypertree verification logic checks whether the signature buffer matches a SHAKE-256 stream over the public message digest, FORS signature, and public keys. It completely omits the mandatory WOTS+ one-time signature chain computations and Merkle tree authentication paths, enabling public-only forgeries without secret key knowledge.

---

### 5. DR22: NIST Draft FIPS 206 FN-DSA (Falcon)
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr22_fndsa_service.cc#L76-L89`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr22_fndsa_service.cc#L76-L89)
* **The Committed Shortcut:**
  ```cpp
  // do_sign reads raw_pk, salt, msg -- secret key is never read:
  const uint8_t *raw_pk = request;
  const uint8_t *salt   = request + pk_bytes + (2 * n);
  const uint8_t *msg    = salt + 40;
  // ...
  alignas(8) int16_t s2[512];
  for (uint32_t i = 0; i < n; ++i) {
      s2[i] = static_cast<int16_t>(static_cast<int8_t>(nonce[2 * i] & 0x1F) - 16);
  }
  ```
* **Vulnerability Analysis:** Signing executes without ingressing or utilizing private key polynomials ($f, g, F, G$). It generates a mock signature vector $s_2$ from public salt and message hash, adjusting a challenge polynomial to satisfy verification. Additionally, the stack array `s2` is fixed at 512 elements; for $n = 1024$ (FN-DSA-1024), the loop executes 1,024 iterations, corrupting the execution stack.

---

### 6. DR30: 3GPP TS 33.501 5G/6G SUCI Co-Processor
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr30_3gpp_suci_service.cc#L64-L72`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr30_3gpp_suci_service.cc#L64-L72)
* **The Committed Shortcut:**
  ```cpp
  // MODE_SUCI_DECAPSULATE_DERIVE
  // Ingests: shared_secret (32 bytes at offset 0), ephem_pubkey (32 bytes at offset 32)
  const uint8_t* ss = request_in;
  const uint8_t* ephem = request_in + 32;
  dr30::derive_suci_keys(ss, ephem, k_enc, k_mac);
  ```
* **Vulnerability Analysis:** The kernel advertises on-device ML-KEM decapsulation of the 5G Subscription Concealed Identifier (SUCI). In reality, the host CPU performs ML-KEM decapsulation and passes the precomputed 32-byte shared secret directly into the kernel at byte offset 0. The NPU only executes ANSI X9.63 KDF and XOR.

---

### 7. DR39: dudect Side-Channel Timing Engine
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr39_dudect_service.cc#L97-L108`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr39_dudect_service.cc#L97-L108)
* **The Committed Shortcut:**
  ```cpp
  // Feeds hardcoded constants into Welford statistical accumulators:
  for (uint32_t i = 0; i < num_trials; ++i) {
      dr39::welford_update(&acc0, base_t0); // base_t0 = 48
  }
  for (uint32_t i = 0; i < num_trials; ++i) {
      dr39::welford_update(&acc1, base_t1); // base_t1 = 48
  }
  ```
* **Vulnerability Analysis:** Instead of measuring hardware cycle counters or execution intervals across fixed vs. random inputs, the kernel feeds static constants `48` and `48` into Welford accumulators, calculating a synthetic $t$-statistic ($t \approx 0.0$) to simulate timing invariance.

---

### 8. DR38: Randomness Statistical Battery & BSI AIS 31
* **Source Location:** [`phoenix_sdr_dsp/pqc/dr38_randomness_abi.py#L233-L234`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/dr38_randomness_abi.py#L233-L234)
* **The Committed Shortcut:**
  ```python
  max_byte_freq = max(histogram)
  entropy_pass = 1 if (max_byte_freq <= (effective_len // 64)) else 0
  ```
* **Vulnerability Analysis:** The ABI checks whether the most frequent byte occurs at most $\text{len}/64$ times and claims this proves Shannon entropy $H \ge 7.95$ bits/byte. This is mathematically false: a stream containing only 64 distinct uniform symbols has $H = \log_2(64) = 6.00$ bits/byte, yet easily passes this test.

---

### 9. DR41: Quantum Key Management System (Q-KMS)
* **Source Location:** [`phoenix_sdr_dsp/pqc/kernels/dr41_qkms_service.cc#L63-L75`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/kernels/dr41_qkms_service.cc#L63-L75)
* **The Committed Shortcut:**
  ```cpp
  // Ingress Vault Bank from request buffer on every call:
  dr41::TileVaultSlot vault[dr41::NUM_VAULT_SLOTS];
  const uint8_t* bank_src = request_in + 128;
  for (size_t i = 0; i < dr41::NUM_VAULT_SLOTS; ++i) {
      vault[i].state = *(const uint32_t*)(bank_src + ...);
  }
  ```
* **Vulnerability Analysis:** The vault slots reside in a temporary stack array populated entirely from the host DMA buffer on each execution. There is no persistent on-tile key residency, hardware rollback protection, or secure key lifecycle enforcement.

---

### 10. DR36: Formal Verification & SMT Proof Models
* **Source Location:** [`phoenix_sdr_dsp/pqc/dr36_formal_verification.py#L90-L115`](file:///C:/Projects/phoenix-npu-pqc/phoenix_sdr_dsp/pqc/dr36_formal_verification.py#L90-L115)
* **The Committed Shortcut:**
  ```python
  # Strided Python loop stepping by 16,384:
  for val in range(min_val, max_val, 16384):
      # ...
  return "100% FORMALLY CERTIFIED", "PROVEN_UNSAT"
  ```
* **Vulnerability Analysis:** Simulating every 16,384th integer in a Python loop was reported as an exhaustive formal proof. Arithmetic overflows, signed modular edge cases, or bit-flip bugs occurring on un-sampled values are completely undetected.

---

## 4. Cross-Repository Audit Records

The quarantine status of these deliverables is recorded across the repository in the following locations:

| Repository File | Location / Identifier | Recorded Status |
| :--- | :--- | :--- |
| [`.agent/blockers.json`](file:///C:/Projects/phoenix-npu-pqc/.agent/blockers.json) | Lines 21–82 | Blockers `DR21-HYPERTREE-FORGERY`, `DR22-SECRET-FREE-SIGNING`, `DR30-HOST-SHARED-SECRET`, `DR31-PARITY-CHECK-AND-PUBLIC-CEK`, `DR34-SENTINEL-BYTE-CHECK`, `DR36-STRIDED-FORMAL-DEFECT`, `DR38-ENTROPY-PREDICATE`, `DR39-HARDCODED-TIMING`, `DR41-EPHEMERAL-VAULT`, `DR42-PARITY-SIGNATURE-CHECK`. |
| [`customer_demo/CUSTOMER_ACCEPTANCE_MATRIX.md`](file:///C:/Projects/phoenix-npu-pqc/customer_demo/CUSTOMER_ACCEPTANCE_MATRIX.md) | Section 2 & Section 3 | Classified as `QUARANTINED` / `BLOCKED_THREE_STRIKES`. Detailed forensic summary for each item. |
| [`customer_demo/GO_NO_GO.md`](file:///C:/Projects/phoenix-npu-pqc/customer_demo/GO_NO_GO.md) | Section 1, 2, 4 | Mandates the global `CUSTOMER READY: NO-GO` verdict due to these 10 deliverables. |
| [`customer_demo/CUSTOMER_SCOPE.json`](file:///C:/Projects/phoenix-npu-pqc/customer_demo/CUSTOMER_SCOPE.json) | Lines 10–28 & entries | Machine-readable breakdown excluding these 270 nominal cases from the customer pass denominator. |
| [`docs/validation/CLEAN_CLONE_VALIDATION.md`](file:///C:/Projects/phoenix-npu-pqc/docs/validation/CLEAN_CLONE_VALIDATION.md) | Section 7 (Lines 118–137) | Published disclosure of quarantined deliverables for fresh-clone onboarding. |

---

## 5. Remediation Feasibility & Engineering Categories

Fixing the quarantined deliverables is technically feasible, but requires distinct engineering approaches based on their underlying architecture:

```
                      TEN QUARANTINED DELIVERABLES
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
   CATEGORY 1                 CATEGORY 2                 CATEGORY 3
 Native Composition      Diagnostic & Tooling       Heavy Mathematical
  (High Feasibility)       (Moderate Effort)       (Complex Engineering)
 ────────────────────    ────────────────────     ───────────────────────
 • DR30 (5G SUCI)        • DR36 (Formal SMT)      • DR21 (SLH-DSA)
 • DR31 (X.509 CMS)      • DR38 (Entropy Model)   • DR22 (FN-DSA / Falcon)
 • DR34 (DICE / TPM)     • DR39 (dudect Cycles)
 • DR42 (Composite Sig)  • DR41 (Q-KMS Slots)
```

### Category 1: High-Feasibility Native Composition (DR30, DR31, DR34, DR42)

**Why they are highly feasible:** The repository already contains authentic, verified on-tile AIE2 implementations of **FIPS 202 (SHA-3/SHAKE)**, **FIPS 203 (ML-KEM Decaps)**, and **FIPS 204 (ML-DSA Verify)**. These four deliverables only need to be wired directly into those existing kernels.

1. **DR30 (3GPP SUCI Co-Processor):**
   * *Architecture:* Route the ingress SUCI ciphertext directly into our existing **DR7 (ML-KEM Decaps)** on-tile pipeline. The decapsulated shared secret remains in Tile (0,2) SRAM and streams into the ANSI X9.63 KDF / XOR tile without CPU exposure.
   * *Effort:* ~1–2 days.
2. **DR31 (X.509 CMS / PKCS#7):**
   * *Architecture:* Route the CMS KEM ciphertext to **DR7 (ML-KEM Decaps)** using the recipient private key in Tile SRAM to recover the true CEK. Route certificate signatures into **DR13 (ML-DSA-44 Verify)**.
   * *Effort:* ~2–3 days.
3. **DR34 (TCG DICE / TPM Attestation):**
   * *Architecture:* Attestation quotes are signed with an Asymmetric Attestation Key (AK). Feed quote digest, public key, and signature directly into **DR13 (ML-DSA Verify)** on tile.
   * *Effort:* ~1–2 days.
4. **DR42 (ANSSI Composite Dual-Signature):**
   * *Architecture:* Combine on-tile **DR13 (ML-DSA Verify)** with an AIE2 scalar/vector Ed25519 or ECDSA P-256 verification kernel. Require both algorithms to write verified non-zero status tokens before releasing output.
   * *Effort:* ~3–4 days.

---

### Category 2: Diagnostic & Methodology Repairs (DR36, DR38, DR39, DR41)

**Why they require moderate effort:** These deliverables suffered from flawed mathematical formulations, simulated accumulators, or memory model limitations rather than algorithmic road-blocks.

1. **DR38 (Randomness Statistical Battery):**
   * *Architecture:* Replace the flawed heuristic with normative **NIST SP 800-90B min-entropy estimators** (Collision Test, Markov Test, Compression Test) and exact Shannon entropy using floating-point base-2 logarithms.
   * *Effort:* ~2 days.
2. **DR39 (dudect Side-Channel Timing):**
   * *Architecture:* Instrument AIE2 hardware performance counter registers (tile cycle timers) or use high-resolution XRT profiling intervals to capture genuine execution cycle deltas over $\ge 100,000$ fixed vs. random executions.
   * *Effort:* ~2–3 days.
3. **DR36 (Formal SMT Models):**
   * *Architecture:* Formulate genuine Z3 / SMT-LIB bit-vector assertions mathematically proving that Barrett reduction, centered coefficient conversions, and NTT index calculations cannot overflow or underflow under any valid input.
   * *Effort:* ~2–3 days.
4. **DR41 (Q-KMS Key Lifecycle):**
   * *Architecture:* Allocate dedicated, locked Tile SRAM memory banks (similar to DR10 Sealed Lifecycle) that persist key slots across dispatches and prevent host memory readback of unencrypted key material.
   * *Effort:* ~3–4 days.

---

### Category 3: Heavyweight Mathematical Schemes (DR21, DR22)

**Why they are complex engineering challenges:** These deliverables are separate cryptographic standards with distinct microarchitectural requirements that test the limits of the XDNA1 / AIE2 architecture.

1. **DR21 (NIST FIPS 205 SLH-DSA / SPHINCS+):**
   * *The Challenge:* Stateless hash-based signatures require evaluating thousands of SHAKE-256 permutations across WOTS+ hash chains, FORS trees, and multi-layer Merkle trees.
   * *The Architecture:* While our AIE2 Keccak core is fast, managing the tree-traversal state within 64 KiB local tile SRAM requires streaming Merkle nodes between compute tiles and Row-1 Shared Memory Tiles (2.5 MiB).
   * *Effort:* ~1–2 weeks.
2. **DR22 (NIST Draft FIPS 206 FN-DSA / Falcon):**
   * *The Challenge:* Falcon relies on double-precision floating-point Fast Fourier Sampling over the FALCON tree. AIE2 compute tiles are fixed-point / integer SIMD engines lacking native 64-bit IEEE 754 floating-point hardware.
   * *The Architecture:* Verification is straightforward (polynomial ring arithmetic). Full *signing*, however, requires either software floating-point emulation or a fixed-point logarithmic FFT sampler, which is one of the most demanding lattice implementations on DSP/AI hardware.
   * *Effort:* ~2–3 weeks.

---

### 6. Recommended Action Plan

To systematically remediate the repository and work toward a full `CUSTOMER READY: GO`:

1. **Phase 1 (Immediate Protocol Scope Expansion - Category 1):**
   * Remediate **DR30 (5G SUCI)**, **DR31 (CMS)**, **DR34 (DICE)**, and **DR42 (Composite Signatures)** by connecting them directly to the validated ML-KEM and ML-DSA AIE2 engines.
2. **Phase 2 (Measurement & Tooling Integrity - Category 2):**
   * Fix **DR38 (Entropy)**, **DR39 (dudect cycle counters)**, **DR36 (Z3 proofs)**, and **DR41 (Persistent slots)**.
3. **Phase 3 (Heavy Schemes - Category 3):**
   * Build the SLH-DSA streaming tree engine (DR21) and restrict DR22 to FN-DSA Verification-Only until the Falcon floating-point sampler is completed.
