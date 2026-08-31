# Release Notes: Version 1.2.0 (PQC, Hybrid QKD, QRNG & Enterprise Token Engine)

> [!NOTE]
> <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=v1.2.0_historical_release; classification=SELF_REPORTED_UNVERIFIED] -->
> [HISTORICAL CLAIM - UNVERIFIED / PENDING PHYSICAL DISPATCH CORROBORATION]
> The historical metrics below reflect pre-refactor self-reported test tallies. Under current Phase A policy, 19 gates are actively evaluated with 0 independently physically verified gates pending driver-level hardware dispatch trace corroboration.

**Release Date:** August 29, 2026
**Target Hardware:** AMD Phoenix / Hawk Point APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1 NPU)
**Historical Scope:** 24 Legacy Hardware Gates tracked across DR0–DR19, DR27

---

## 1. Executive Summary

Version 1.2.0 of `phoenix-npu-pqc` expands the Post-Quantum Cryptography (PQC) and Quantum Key Distribution (QKD) hardware engine on the AMD Phoenix NPU (AIE2 / XDNA1) by introducing **Milestone DR27 (Palo Alto Networks QRNG-OPENAPI v1.0 & On-Device SRAM Entropy Reservoir)** and **Milestone DR23 (OpenSSL 3.x Native Provider & OASIS PKCS#11 v3.0 HSM Python Prototypes)**.

With these additions, enterprise software (Nginx, Envoy, Apache, OpenSSH) and standard cryptographic token interfaces can now harness on-device lattice cryptography and quantum entropy with zero host CPU cryptographic execution.

---

## 2. Key New Features in v1.2.0

### Milestone DR27: QRNG-OPENAPI v1.0 & On-Chip Key Reservoir (Gate 23)
* **Standards Reference**: Palo Alto Networks QRNG-OPENAPI v1.0, NIST SP 800-90B, and NIST SP 800-56C Rev. 2.
* **Sealed Ingress Daemon (`dr27_qrng_daemon.py`)**:
  - Implements `POST /v1/entropy` and `GET /v1/healthtest` endpoints.
  - Performs continuous on-the-fly NIST SP 800-90B health evaluations (Repetition Count Test & Adaptive Proportion Test).
  - Streams entropy blocks via zero-copy XRT ObjectFifo DMA into locked AIE2 SRAM with instant host memory zeroization.
* **On-Chip Token-Bucket Reservoir (`dr27_qrng_reservoir_service.cc`)**:
  - Maintains a 16-slot token bucket resident in tile SRAM.
  - Implements 5% low-water mark degradation (State 1: Degraded Mode A) and 30% high-water mark recovery (State 0: Full Hybrid) to eliminate state flapping under bursty network loads.
  - Enforces instant hardware register zeroization (`0x00` overwrite) on reset or panic.

### Milestone DR23: OpenSSL 3.x Provider & PKCS#11 HSM Token [HOST PYTHON REFERENCE / PROTOTYPE]
* **Standards Reference**: OpenSSL 3.0+ Provider API & OASIS PKCS#11 v3.0 Cryptoki.
* **OpenSSL 3.x Provider Prototype (`dr23_openssl_provider.py`)**:
  - Implements standard `OSSL_PROVIDER` dispatch tables (`OSSL_FUNC_PROVIDER_GET_PARAMS`, `OSSL_FUNC_PROVIDER_QUERY_OPERATION`).
  - Exposes `OSSL_OP_KEM` (14): `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024`, `X25519-ML-KEM-768`, `QKD-ML-KEM-768`.
  - Exposes `OSSL_OP_SIGNATURE` (12): `ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87`.
  - Exposes `OSSL_OP_KEYMGMT` (10): Keypair generation, import/export, and instant zeroization.
* **OASIS PKCS#11 v3.0 HSM Cryptoki Token (`dr23_pkcs11_hsm.py`)**:
  - Token and session lifecycle management (`C_Initialize`, `C_GetInfo`, `C_GetSlotList`, `C_GetTokenInfo`, `C_OpenSession`, `C_Login`).
  - Operations: `C_GenerateKeyPair`, `C_Sign`, `C_Verify`, and `C_DeriveKey`.
  - Automatic DR10 hardware register zeroization upon session close or logout.

---

## 3. Historical Scope & Gate Overview

The historical baseline evaluated the following modules across the AMD Phoenix AIE2 architecture:

1. **DR0–DR10**: Foundation, ring arithmetic, ML-KEM-512 pipeline, SHA-3/SHAKE services, and sealed lifecycle management.
2. **DR11–DR15**: ML-DSA-44, ML-DSA-65, and ML-DSA-87 KeyGen, Sign, and Verify services.
3. **DR16–DR19**: ETSI QKD 014 ingress, ML-DSA QKD control, NIST SP 800-56C dual key combiner, and full-duplex session orchestrator.
4. **DR27**: QRNG-OPENAPI entropy ingress and SRAM reservoir core.
