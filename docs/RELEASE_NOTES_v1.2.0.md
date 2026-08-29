# Release Notes: Version 1.2.0 (PQC, Hybrid QKD, QRNG & Enterprise Token Engine)

**Release Date:** August 29, 2026  
**Target Hardware:** AMD Phoenix / Hawk Point APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1 NPU)  
**Silicon Verification:** 25 / 25 Gates PASS (100.00%) · 851 / 851 Test Cases Bit-Exact on Physical Silicon in 33.21s  
**DOI:** [10.5281/zenodo.22162273](https://doi.org/10.5281/zenodo.22162273)  

---

## 1. Executive Summary

Version 1.2.0 of `phoenix-npu-pqc` expands the world's first 100% device-resident Post-Quantum Cryptography (PQC) and Quantum Key Distribution (QKD) hardware engine on the AMD Phoenix NPU (AIE2 / XDNA1) by introducing **Milestone DR27 (Palo Alto Networks QRNG-OPENAPI v1.0 & On-Device SRAM Entropy Reservoir)** and **Milestone DR23 (OpenSSL 3.x Native Provider Plugin & OASIS PKCS#11 v3.0 HSM Cryptoki Token)**.

With these additions, enterprise software (Nginx, Envoy, Apache, OpenSSH) and standard cryptographic token interfaces can now harness 100% on-device lattice cryptography and quantum entropy with zero host CPU cryptographic execution.

---

## 2. Key New Features in v1.2.0

### Milestone DR27: QRNG-OPENAPI v1.0 & On-Chip Key Reservoir (Gate 23)
* **Standards Conformance**: Palo Alto Networks QRNG-OPENAPI v1.0, NIST SP 800-90B, and NIST SP 800-56C Rev. 2.
* **Sealed Ingress Daemon (`dr27_qrng_daemon.py`)**:
  - Implements `POST /v1/entropy` and `GET /v1/healthtest` endpoints.
  - Performs continuous on-the-fly NIST SP 800-90B health evaluations (Repetition Count Test & Adaptive Proportion Test).
  - Streams entropy blocks via zero-copy XRT ObjectFifo DMA into locked AIE2 SRAM with instant host memory zeroization.
* **On-Chip Token-Bucket Reservoir (`dr27_qrng_reservoir_service.cc`)**:
  - Maintains a 16-slot token bucket resident in tile SRAM.
  - Implements 5% low-water mark degradation (State 1: Degraded Mode A) and 30% high-water mark recovery (State 0: Full Hybrid) to eliminate state flapping under bursty network loads.
  - Enforces instant hardware register zeroization (`0x00` overwrite) on reset or panic.

### Milestone DR23: OpenSSL 3.x Native Provider & PKCS#11 HSM Token (Gate 24)
* **Standards Conformance**: OpenSSL 3.0+ Provider API & OASIS PKCS#11 v3.0 Cryptoki.
* **OpenSSL 3.x Native Provider (`dr23_openssl_provider.py` & `phoenix_pqc_provider.c`)**:
  - Implements standard `OSSL_PROVIDER` dispatch tables (`OSSL_FUNC_PROVIDER_GET_PARAMS`, `OSSL_FUNC_PROVIDER_QUERY_OPERATION`).
  - Exposes `OSSL_OP_KEM` (14): `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024`, `X25519-ML-KEM-768`, `QKD-ML-KEM-768`.
  - Exposes `OSSL_OP_SIGNATURE` (12): `ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87`.
  - Exposes `OSSL_OP_KEYMGMT` (10): Keypair generation, import/export, and instant zeroization.
  - C ABI entry point `OSSL_provider_init` for direct drop-in enterprise acceleration.
* **OASIS PKCS#11 v3.0 HSM Cryptoki Token (`dr23_pkcs11_hsm.py`)**:
  - Token and session lifecycle management (`C_Initialize`, `C_GetInfo`, `C_GetSlotList`, `C_GetTokenInfo`, `C_OpenSession`, `C_Login`).
  - Hardware-resident operations: `C_GenerateKeyPair`, `C_Sign`, `C_Verify`, and `C_DeriveKey`.
  - Automatic DR10 hardware register zeroization upon session close or logout.

---

## 3. Master Silicon Validation Matrix (25 Gates · 851 Test Cases)

```
================================================================================
100% ON-DEVICE PQC & HYBRID QKD MASTER SILICON VALIDATION SUITE
Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)
Scope: Full NIST FIPS 202, 203, 204, ETSI GS QKD 014, QRNG-OPENAPI, OpenSSL 3.x, PKCS#11, SP 800-56C (DR0–DR27)
================================================================================
[+] Gate 00: DR0 M33 Ring Product                        : PASS ( 0.91s)
[+] Gate 01: DR1 ML-DSA-44 ExpandA                       : PASS ( 0.75s)
[+] Gate 02: DR2a ML-KEM-512 SampleNTT                   : PASS ( 0.69s)
[+] Gate 03: DR2b ML-KEM-512 CBD3/NTT                    : PASS ( 0.71s)
[+] Gate 04: DR2c ML-KEM-512 KeyGen Row                  : PASS ( 0.71s)
[+] Gate 05: DR2d ML-KEM-512 K-PKE KeyGen                : PASS ( 0.78s)
[+] Gate 06: DR3 ML-KEM-512 K-PKE Encrypt                : PASS ( 0.75s)
[+] Gate 07: DR4 ML-KEM-512 K-PKE Decrypt                : PASS ( 0.71s)
[+] Gate 08: DR5 ML-KEM-512 ML-KEM KeyGen                : PASS ( 0.76s)
[+] Gate 09: DR6 ML-KEM-512 ML-KEM Encaps                : PASS ( 0.75s)
[+] Gate 10: DR7 ML-KEM-512 ML-KEM Decaps                : PASS ( 0.80s)
[+] Gate 11: DR8 ML-KEM-768 & 1024 Expansion             : PASS ( 1.82s)
[+] Gate 12: DR9 FIPS 202 SHA-3/SHAKE Service            : PASS ( 0.86s)
[+] Gate 13: DR10 Sealed Lifecycle & Key Sources         : PASS ( 0.80s)
[+] Gate 14: DR11 ML-DSA-44 KeyGen                       : PASS ( 0.89s)
[+] Gate 15: DR12 ML-DSA-44 Sign                         : PASS ( 2.30s)
[+] Gate 16: DR13 ML-DSA-44 Verify                       : PASS ( 1.35s)
[+] Gate 17: DR14 ML-DSA-65 (KeyGen, Sign, Verify)       : PASS ( 4.84s)
[+] Gate 18: DR15 ML-DSA-87 (KeyGen, Sign, Verify)       : PASS ( 3.56s)
[+] Gate 19: DR16 ETSI GS QKD 014 Sealed Ingress         : PASS ( 0.70s)
[+] Gate 20: DR17 ML-DSA Asymmetric QKD Control          : PASS ( 2.71s)
[+] Gate 21: DR18 NIST SP 800-56C Dual Combiner          : PASS ( 1.11s)
[+] Gate 22: DR19 Hybrid QKD-PQC Session Orchestrator    : PASS ( 0.65s)
[+] Gate 23: DR27 QRNG-OPENAPI & Entropy Reservoir       : PASS ( 1.23s)
[+] Gate 24: DR23 OpenSSL 3.x Provider & PKCS#11 HSM     : PASS ( 2.09s)
================================================================================
MASTER SILICON SUITE RESULT: 25/25 GATES PASS (100.00%) in 33.21s
TOTAL VERIFIED TEST COUNT: 851 / 851 PASS (100.00% Physical Silicon Correctness)
================================================================================
```
