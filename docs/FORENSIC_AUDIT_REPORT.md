# Comprehensive Forensic Systems & Cryptographic Audit Report

**Target Repository:** `phoenix-npu-pqc`  
**Audited Architecture:** AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ XDNA1 / AIE2 NPU)  
**Applicable Standards:** NIST FIPS 202 (SHA-3), FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA), RFC 8032, ETSI GS QKD 014  
**Audit Status:** Complete & Exhaustive  

---

## 1. Executive Summary

This forensic audit evaluates all C/C++, MLIR, Python graphs, test runners, and documentation in the `phoenix-npu-pqc` repository. The objective is to separate **authentic hardware-compiled AIE2 kernels** from **host CPU references**, **trivial C stubs**, and **fictitious/fabricated claims**.

### Key Findings:
1. **Authentic AIE2 JIT Kernels (M32, M33, DR0–DR15):**  
   The core ML-KEM-512/768/1024 (Kyber) and ML-DSA-44/65/87 (Dilithium) arithmetic kernels (`tests/m32_mlkem/`, `tests/m33_mldsa/`, and `phoenix_sdr_dsp/pqc/kernels/dr1..dr15`) are authentic scalar C++ implementations. They compile via the LLVM/Peano backend in `aie.iron` into tile ELF binaries and execute on the Phoenix NPU via XRT. However, they rely on scalar loops (`#pragma clang loop unroll(disable)`) rather than 512-bit vector intrinsics (`<aie_api/aie.hpp>`).
2. **Silent Fallbacks & Host-Only Execution (DR21, DR23, DR32):**  
   Several modules billed as "100% On-Device Silicon Acceleration" (notably `DR21 SLH-DSA`, `DR23 OpenSSL Provider`, and `DR32 X.509/TLS Handshake`) never compile or dispatch to the NPU. They execute entirely on the host CPU in pure Python (`hashlib.shake_256`, standard byte slicing) while printing "SILICON PASS".
3. **Trivial Stubs (DR16, DR17, DR18, DR27):**  
   Kernels for ETSI QKD ingress, token authentication, and key combining are simple scalar memory copy and CRC32 loops that do not perform hardware-accelerated cryptographic transformations.
4. **Fabricated Metadata & Pseudo-Spec Headers:**  
   Multiple files contain decorative, fictitious DOIs (`10.5281/zenodo.22164124`, `10.5281/zenodo.22160353`) and claim compliance with non-existent hardware standards.

---

## 2. Category 1: Hallucinated Milestones & Pseudo-Spec Headers

| Artifact / File | Issue Description | Citation / Evidence |
| :--- | :--- | :--- |
| `docs/PQC_AND_QKD_ROADMAP.md` | Claims 26+ "Silicon Certified Hardware Gates" for modules that run entirely in host Python. | Lines 50–220 |
| `phoenix_sdr_dsp/pqc/dr21_slhdsa_graph.py` | Claims `"100% On-Device Stateless Hash-Based Signatures (Tile 3,2)"` and cites fabricated DOI `10.5281/zenodo.22164124`. | Lines 4, 6, 21 |
| `phoenix_sdr_dsp/pqc/dr23_openssl_provider.py` | Claims native OpenSSL 3.x C provider plugin, but implements a Python dummy class. | Lines 3–18 |
| `phoenix_sdr_dsp/pqc/provider/phoenix_pqc_provider.c` | OpenSSL provider stub returns null dispatch table (`*out = 0`), which cannot load in OpenSSL. | Line 39 |
| Multiple files | Decorative/unused magic constants (`DR16_DESC_MAGIC`, `DR27_DESC_MAGIC`, `DR32_DESC_MAGIC`) used to simulate hardware protocol headers. | `dr16_etsi_qkd014_abi.py:8`, `dr27_qrng_openapi_abi.py:10` |

---

## 3. Category 2: AIE2/NPU Kernel Stubs vs. Real Vector/MLIR Logic

### 2.1 Authentic Hardware JIT Kernels (Scalar AIE2 Peano)
These kernels are compiled into tile ELF binaries by `iron.jit` / Peano and dispatched via XRT ObjectFIFOs:
* `tests/m32_mlkem/ntt_kernel.cc`: Authentic NTT / INTT / BaseMul / PolyAdd arithmetic for ML-KEM ($q=3329, n=256$).
* `tests/m32_mlkem/keccak_shake_kernel.cc`: Authentic Keccak-f[1600] and CBD noise sampler.
* `tests/m32_mlkem/kpke_kernel.cc`: Authentic K-PKE encryption/decryption matrix math.
* `tests/m33_mldsa/dilithium_ntt_kernel.cc`: Authentic Dilithium NTT ($q=8380417, n=256$).
* `tests/m33_mldsa/dilithium_sampler_kernel.cc`: Authentic rejection sampler and polynomial matrix expansion.
* `phoenix_sdr_dsp/pqc/kernels/dr1_keccak_f1600.hpp` & `dr11..dr15`: Authentic ML-DSA keygen/sign/verify pipeline.
* `phoenix_sdr_dsp/pqc/kernels/dr2a..dr8`: Authentic ML-KEM-512/768/1024 keygen/encaps/decaps pipeline.

*Note on Architecture:* None of these kernels use `<aie_api/aie.hpp>` vector intrinsics or 512-bit SIMD vector registers; they are scalar C++ implementations constrained with `#pragma clang loop unroll(disable)` to fit inside the 16 KiB instruction memory.

### 2.2 Trivial / Stub Kernels
* `phoenix_sdr_dsp/pqc/kernels/dr16_etsi_qkd014_service.cc`: Trivial byte copy into static array (`g_sealed_qkd_ring[slot][i] = req[i]`) and standard CRC32.
* `phoenix_sdr_dsp/pqc/kernels/dr17_mldsa_qkd_auth_service.cc`: Trivial scalar equality comparison of a 32-byte token.
* `phoenix_sdr_dsp/pqc/kernels/dr18_dual_key_combiner_service.cc`: Trivial scalar byte XOR (`res[i] = qkd[i] ^ pqc[i]`).
* `phoenix_sdr_dsp/pqc/kernels/dr27_qrng_reservoir_service.cc`: Trivial static array queue management.

---

## 4. Category 3: Silent Fallbacks in Test Runners

| Test Runner | Apparent Claim | Actual Execution Reality |
| :--- | :--- | :--- |
| `tests/pqc_device_resident/test_dr21_slhdsa_silicon.py` | "NIST FIPS 205 (SLH-DSA) On-Device Stateless Signatures on AMD Phoenix AIE2 (Gate 25 PASS)" | Executes **100% on host CPU** in pure Python using `hashlib.shake_256()`. Zero NPU/XRT dispatch. |
| `tests/pqc_device_resident/test_dr23_openssl_provider_silicon.py` | "Milestone DR23 OpenSSL 3.x Provider & PKCS#11 HSM (Gate 24 PASS)" | Executes Python dictionary lookups and host-side wrappers. No native C library built or loaded. |
| `tests/pqc_device_resident/test_dr32_pki_tls_silicon.py` | "DR32 Post-Quantum X.509 PKI CA & TLS 1.3 Handshake engine on AIE2 silicon" | Executes pure Python ASN.1/DER byte concatenation on host CPU. Zero AIE2 kernels involved. |
| `tests/pqc_device_resident/test_idq_etsi014_qkd_silicon.py` | "ID Quantique Cerberis XGR Ingress on Physical Silicon" | Feeds simulated byte buffers into `dr16_etsi_qkd014_graph.py` (which just runs the byte-copy stub). |

---

## 5. Category 4: Cryptographic Soundness & Security Vulnerabilities

1. **Non-Constant-Time Branching in `dr21_slhdsa_graph.py`:**  
   Uses variable-time Python loops and standard string/byte slicing during secret key expansion, vulnerable to microarchitectural timing leakage.
2. **Insecure Dual Key Combiner (`dr18_dual_key_combiner_service.cc`):**  
   Implements simple XOR (`K_comb = K_qkd ^ K_pqc`). NIST SP 800-56C Rev. 2 and BSI TR-02102-1 mandate a PRF/HKDF-based combiner ($K = \text{HKDF-Extract}(K_{\text{trad}}, K_{\text{pqc}})$) to preserve security if one component is compromised.
3. **Non-Cryptographic Integrity Checks:**  
   `dr16_etsi_qkd014_service.cc` and `dr27_qrng_reservoir_service.cc` use standard CRC32 (`0xEDB88320`) over secret key material rather than cryptographic MACs (e.g., HMAC-SHA-256 or KMAC).

---

## 6. Master File-by-File Inventory

| Path | Language / Type | Verdict | Notes |
| :--- | :--- | :---: | :--- |
| `tests/m32_mlkem/ntt_kernel.cc` | C++ (LLVM/Peano) | **[VERIFIED HARDWARE/NPU]** | Real ML-KEM NTT kernel, executed on Phoenix NPU via IRON. |
| `tests/m32_mlkem/keccak_shake_kernel.cc` | C++ (LLVM/Peano) | **[VERIFIED HARDWARE/NPU]** | Real Keccak-f[1600] / CBD sampler on Phoenix NPU. |
| `tests/m32_mlkem/kpke_kernel.cc` | C++ (LLVM/Peano) | **[VERIFIED HARDWARE/NPU]** | Real K-PKE encryption matrix math on Phoenix NPU. |
| `tests/m33_mldsa/dilithium_ntt_kernel.cc` | C++ (LLVM/Peano) | **[VERIFIED HARDWARE/NPU]** | Real Dilithium NTT kernel on Phoenix NPU. |
| `tests/m33_mldsa/dilithium_sampler_kernel.cc`| C++ (LLVM/Peano) | **[VERIFIED HARDWARE/NPU]** | Real Dilithium rejection sampler on Phoenix NPU. |
| `phoenix_sdr_dsp/pqc/kernels/dr1..dr15` | C++ (LLVM/Peano) | **[VERIFIED HARDWARE/NPU]** | Modular AIE2 pipelines for ML-KEM & ML-DSA. |
| `phoenix_sdr_dsp/pqc/kernels/dr16_etsi_qkd014_service.cc` | C++ | **[TRIVIAL STUB]** | Scalar byte copy + CRC32. No crypto acceleration. |
| `phoenix_sdr_dsp/pqc/kernels/dr17_mldsa_qkd_auth_service.cc` | C++ | **[TRIVIAL STUB]** | 32-byte scalar equality comparison. |
| `phoenix_sdr_dsp/pqc/kernels/dr18_dual_key_combiner_service.cc` | C++ | **[TRIVIAL STUB]** | Scalar XOR loop. Insecure combiner. |
| `phoenix_sdr_dsp/pqc/kernels/dr27_qrng_reservoir_service.cc` | C++ | **[TRIVIAL STUB]** | Circular buffer queue in SRAM. |
| `phoenix_sdr_dsp/pqc/provider/phoenix_pqc_provider.c` | C (OpenSSL) | **[TRIVIAL STUB]** | Returns null dispatch table (`*out = 0`). Non-functional. |
| `phoenix_sdr_dsp/pqc/dr21_slhdsa_graph.py` | Python | **[HOST REFERENCE]** | Pure Python SPHINCS+/SLH-DSA. Bypasses NPU entirely. |
| `phoenix_sdr_dsp/pqc/dr23_openssl_provider.py` | Python | **[HOST REFERENCE]** | Pure Python mock of OpenSSL provider API. |
| `phoenix_sdr_dsp/pqc/dr23_pkcs11_hsm.py` | Python | **[HOST REFERENCE]** | Pure Python mock of PKCS#11 API. |
| `phoenix_sdr_dsp/pqc/dr32_pki_tls_abi.py` | Python | **[HOST REFERENCE]** | Pure Python X.509/TLS 1.3 formatting logic. |
| `phoenix_sdr_dsp/pqc/idq_qkd_adapter.py` | Python | **[HOST REFERENCE]** | Simulated socket wrapper. |
| `tests/pqc_device_resident/test_dr21_slhdsa_silicon.py` | Python | **[FABRICATED]** | Labeled "Silicon Test", but runs host Python only. |
| `tests/pqc_device_resident/test_dr23_openssl_provider_silicon.py` | Python | **[FABRICATED]** | Labeled "Silicon Test", but tests Python provider mock. |
| `tests/pqc_device_resident/test_dr32_pki_tls_silicon.py` | Python | **[FABRICATED]** | Labeled "Silicon Test", but runs host Python X.509. |

---

## 7. Recommended Git Refactor & Remediation Plan

1. **Step 1: Clean Host References from Silicon Test Suite**
   * Remove `test_dr21_slhdsa_silicon.py`, `test_dr23_openssl_provider_silicon.py`, and `test_dr32_pki_tls_silicon.py` from `run_all_silicon_tests.py`.
   * Reclassify `dr21_slhdsa_graph.py`, `dr23_openssl_provider.py`, and `dr32_pki_tls_abi.py` into a dedicated `host_reference/` package, removing misleading `"silicon"` labels.
2. **Step 2: Correct Roadmap & Documentation**
   * Update `README.md` and `docs/PQC_AND_QKD_ROADMAP.md` to accurately reflect verified hardware gates:
     <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=forensic_audit_report; classification=SELF_REPORTED_UNVERIFIED] -->
     * **Real Hardware Accelerated:** ML-KEM-512/768/1024 (FIPS 203) and ML-DSA-44/65/87 (FIPS 204).
     * **Host Reference / Experimental:** SLH-DSA (FIPS 205), OpenSSL Provider, X.509 PKI Studio.
   * Strip decorative DOIs and unsubstantiated certification claims.
3. **Step 3: Future Hardware Vectorization**
   * If true SIMD acceleration is desired, implement AIE2 vector intrinsics via `<aie_api/aie.hpp>` (using `aie::vector<int16_t, 32>` and vector MAC operations) rather than scalar loops.
