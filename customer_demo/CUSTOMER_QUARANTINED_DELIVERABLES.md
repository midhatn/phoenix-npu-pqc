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

### 2. Master Quarantined Deliverables Summary

### Active Quarantined Deliverables (2 Remaining)

| Milestone | Claimed Operation | Primary Standard | Exact File Location | Defect Mechanism | Remediation Category | Current Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **DR39** | dudect Side-Channel Timing | dudect / ISO 17825 | `phoenix_sdr_dsp/pqc/kernels/dr39_dudect_service.cc` | Hardcoded constant cycle counts (`48/48`) in accumulator; missing unprivileged cycle counter | **Category 2** | `BLOCKED_THREE_STRIKES` |
| **DR41** | Quantum Key Management (Q-KMS) | ETSI GS QKD 014 | `phoenix_sdr_dsp/pqc/kernels/dr41_qkms_service.cc` | Ephemeral vault re-ingressed from host; persistent sealed enclave unsupported across dispatches | **Category 2** | `BLOCKED_THREE_STRIKES` |

### Remediated Deliverables: Native Hardware Composition & Formal Tooling (8 Remediated)

| Milestone | Deliverable | Primary Standard | Connected Hardware Primitives / Formal Engine | Test Execution Outcome | Remediated Status |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **DR21** | NIST FIPS 205 SLH-DSA | FIPS 205 (SPHINCS+) | Multi-Tile Streaming Hypertree on Row-1 MemTiles (< 4 KiB SRAM) | 30 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR22** | NIST Draft FIPS 206 FN-DSA | Draft FIPS 206 (Falcon) | AIE2 Integer Ring Verification $\mathbb{Z}_{12289}$; BSS scratchpad allocation | 30 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR30** | 3GPP 5G/6G Core Network SUCI | 3GPP TS 33.501 | AIE2 ML-KEM-512 Decaps (DR7) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR31** | X.509 PQ Certificates & CMS | RFC 5280 / RFC 5652 | AIE2 ML-DSA-44 Verify (DR13) + ML-KEM-512 Decaps (DR7) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR34** | TCG DICE / TPM Attestation | TCG DICE Architecture | AIE2 ML-DSA-44 Verify (DR13) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR36** | Formal Verification & SMT Models | SMT-LIB 2.0 / Z3 | Z3 BitVector (QF_BV) & Linear Int (QF_LIA) Prover | 8 matching, 0 failing (exit 0) | **REMEDIATED** |
| **DR38** | Randomness Statistical Battery | NIST SP 800-22 / AIS 31 | AIE2 Q16 Fixed-Point Shannon Entropy (AIS 31 T8) | 25 matching, 0 failing (exit 0) | **REMEDIATED** |
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

                      TEN AUDITED DELIVERABLES STATUS
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
    CATEGORY 1                 CATEGORY 2                 CATEGORY 3
  Native Composition      Diagnostic & Tooling       Heavy Mathematical
   [100% REMEDIATED]       [2 REMEDIATED / 2 BLK]     [100% REMEDIATED]
  ────────────────────    ────────────────────     ───────────────────────
  • DR30 (5G SUCI) [PASS] • DR36 (Formal SMT)[PASS]• DR21 (SLH-DSA) [PASS]
  • DR31 (X.509)   [PASS] • DR38 (AIS 31 T8) [PASS]• DR22 (FN-DSA)  [PASS]
  • DR34 (DICE)    [PASS] • DR39 (dudect) [BLOCKED]
  • DR42 (Dual-Sig)[PASS] • DR41 (Q-KMS)  [BLOCKED]

### Category 1: High-Feasibility Native Composition (DR30, DR31, DR34, DR42) — [REMEDIATED]

**Remediation Architecture:** The repository contains authentic, verified on-tile AIE2 implementations of **FIPS 202 (SHA-3/SHAKE)**, **FIPS 203 (ML-KEM Decaps)**, and **FIPS 204 (ML-DSA Verify)**. These four deliverables are wired directly into those existing kernels:

1. **DR30 (3GPP SUCI Co-Processor) — [REMEDIATED]:**
   * *Architecture:* Routes the ingress SUCI ciphertext directly into our existing **DR7 (ML-KEM Decaps)** on-tile pipeline. The decapsulated shared secret remains in Tile (0,2) SRAM and streams into the ANSI X9.63 KDF / XOR tile without CPU exposure. Verified 25/25 bit-exact.
2. **DR31 (X.509 CMS / PKCS#7) — [REMEDIATED]:**
   * *Architecture:* Routes the CMS KEM ciphertext to **DR7 (ML-KEM Decaps)** using the recipient private key in Tile SRAM to recover the true CEK. Routes certificate signatures into **DR13 (ML-DSA-44 Verify)**. Verified 25/25 bit-exact.
3. **DR34 (TCG DICE / TPM Attestation) — [REMEDIATED]:**
   * *Architecture:* Attestation quotes are signed with an Asymmetric Attestation Key (AK). Feeds quote digest, public key, and signature directly into **DR13 (ML-DSA Verify)** on tile. Verified 25/25 bit-exact.
4. **DR42 (ANSSI Composite Dual-Signature) — [REMEDIATED]:**
   * *Architecture:* Combines on-tile **DR13 (ML-DSA Verify)** with scalar Ed25519 point multiplication. Requires both algorithms to write verified non-zero status tokens before releasing output. Verified 25/25 bit-exact.

---

### Category 2: Diagnostic & Methodology Repairs (DR36, DR38, DR39, DR41)

1. **DR38 (Randomness Statistical Battery & BSI AIS 31) — [REMEDIATED]:**
   * *Architecture:* Replaced the flawed heuristic with authentic **BSI AIS 31 Test T8 Shannon entropy** ($H = -\sum p_i \log_2 p_i$) and NIST SP 800-90B min-entropy health checks, utilizing a 65-entry Q16 fixed-point $\log_2$ lookup table on AIE2 hardware. Verified 25/25 bit-exact on Phoenix silicon.
2. **DR36 (Formal SMT Models) — [REMEDIATED]:**
   * *Architecture:* Formulated genuine Z3 / SMT-LIB bit-vector assertions (QF_BV and QF_LIA) mathematically proving that Barrett reduction, centered coefficient conversions, and NTT butterfly invertibility cannot overflow or underflow under any valid input over unbounded domains. Verified 8/8 contract tests.
3. **DR39 (dudect Side-Channel Timing) — [BLOCKED_THREE_STRIKES]:**
   * *Status:* AIE2 toolchain lacks unprivileged cycle counter register (`undefined symbol: get_cycles()`). Maintained in active quarantine under the Three-Strike Rule pending host/driver ETW performance counter tracing.
4. **DR41 (Q-KMS Key Lifecycle) — [BLOCKED_THREE_STRIKES]:**
   * *Status:* Discrete user-mode graph dispatches re-initialize tile state; unprivileged driver lacks persistent sealed hardware enclave in SRAM across separate process executions. Maintained in active quarantine under the Three-Strike Rule.

---

### Category 3: Heavyweight Mathematical Schemes (DR21, DR22) — [REMEDIATED]

1. **DR21 (NIST FIPS 205 SLH-DSA / SPHINCS+) — [REMEDIATED]:**
   * *Architecture:* Designed streaming multi-tile hypertree architecture utilizing Row-1 Shared Memory Tiles (following `phoenix-sdr-dsp`). Decomposes layer-by-layer XMSS/WOTS+ verification within a 4 KiB SRAM footprint without buffering full signatures in tile SRAM. Verified 30/30 bit-exact on physical Phoenix silicon.
2. **DR22 (NIST Draft FIPS 206 FN-DSA / Falcon) — [REMEDIATED]:**
   * *Architecture:* Decoupled `FN-DSA.Verify` to authentic integer ring arithmetic in $\mathbb{Z}_{12289}[X]/(X^n+1)$, eliminating floating-point dependencies. Implemented normative Draft FIPS 206 decoders alongside official NIST Falcon Round 3 decoders (harmonizing standalone 0x39 and NIST .rsp 0x29 header bytes). Relocated scratchpads to aligned tile SRAM BSS memory with `stack_size=0x1800`. Verified 30/30 bit-exact on physical Phoenix silicon.

---

### 6. Action Plan Status

- **Phase 1 (Immediate Protocol Scope Expansion - Category 1):** COMPLETED (DR30, DR31, DR34, DR42 remediated and passing).
- **Phase 2 (Measurement & Tooling Integrity - Category 2):** COMPLETED for DR36 and DR38; DR39 and DR41 quarantined under Three-Strike Rule.
- **Phase 3 (Heavy Schemes - Category 3):** COMPLETED (DR21 streaming hypertree and DR22 integer ring verification remediated and passing on silicon).
