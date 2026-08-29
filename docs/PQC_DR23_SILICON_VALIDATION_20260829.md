# DR23 Silicon Validation Report: OpenSSL 3.x Native Provider & PKCS#11 HSM

**Date:** 2026-08-29  
**Platform:** AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1 Architecture)  
**Host Environment:** Windows 11 x86_64, MLIR-AIE 1.4.1, XRT Native Runtime  
**Status:** **CLOSED & PHYSICALLY VALIDATED ON SILICON (6/6 PASS across OpenSSL 3.x Provider and PKCS#11 Token interfaces)**  
**DOI:** [10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124)

---

## 1. Validation Scope

Milestone **DR23 (Gate 24)** evaluated standard enterprise interface integration:
1. **Provider Discovery & Parameter Query**: Verifies `OSSL_FUNC_PROVIDER_GET_PARAMS` and algorithm tables.
2. **OpenSSL KEM KeyGen & Encaps/Decaps**: Validates `EVP_KEM` dispatch to AIE2 hardware.
3. **OpenSSL Signature KeyGen & Sign/Verify**: Validates `EVP_SIGNATURE` dispatch to AIE2 hardware.
4. **PKCS#11 Token Lifecycle & PIN Auth**: Validates `C_Initialize`, `C_Login` (PIN `1234`), and `C_Logout`.
5. **PKCS#11 On-Token Keypair Generation**: Validates hardware-bound key generation in Tile SRAM.
6. **PKCS#11 On-Token Signing & Hardware Zeroization**: Validates `C_Sign`, signature verification, and memory wipe.

---

## 2. Test Results Summary

| Test Case | Target Subsystem | Verified Operation | Silicon Result | Status | Hardware Runtime |
|---|---|---|---|:---:|:---:|
| **Test 01** | `OpenSSL Provider` | Parameter queries, capability tables, hardware tags | PASS | **100% Pass** | 0.05s |
| **Test 02** | `OpenSSL KEM` | ML-KEM-512/768/1024 KeyGen, Encaps, Constant-Time Decaps | PASS | **100% Pass** | 0.65s |
| **Test 03** | `OpenSSL Sign` | ML-DSA-44/65/87 and SLH-DSA KeyGen, Sign, Verify | PASS | **100% Pass** | 0.82s |
| **Test 04** | `PKCS#11 Token` | Token initialization, PIN authentication, session slots | PASS | **100% Pass** | 0.05s |
| **Test 05** | `PKCS#11 KeyGen` | On-token KEM and DSA key generation in SRAM | PASS | **100% Pass** | 0.35s |
| **Test 06** | `PKCS#11 Zeroize` | On-token signing, verification, and DR10 memory scrub | PASS | **100% Pass** | 0.45s |
| **TOTAL DR23** | **Gate 24 (Enterprise)** | **OpenSSL 3.x Provider & PKCS#11 HSM Token** | **6 / 6 PASS** | **100% Pass Rate** | **2.37s** |
