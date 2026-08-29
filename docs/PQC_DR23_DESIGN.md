# DR23 Architecture & Design: OpenSSL 3.x Native Provider & OASIS PKCS#11 v3.0 HSM Token on AMD Phoenix NPU (AIE2)

<div align="center">

![Standard: OpenSSL 3.x Provider](https://img.shields.io/badge/Standard-OpenSSL%203.x%20Provider%20API-red)
![Standard: OASIS PKCS#11 v3.0](https://img.shields.io/badge/Standard-OASIS%20PKCS%2311%20v3.0%20HSM-blue)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary

Milestone **DR23** delivers the enterprise drop-in consumption layer for the AMD Phoenix NPU PQC appliance:
1. **OpenSSL 3.x Native Provider (`phoenix_pqc_provider`)**: Dispatches standard `EVP_KEM` (ML-KEM-512/768/1024, X25519-ML-KEM-768, QKD-ML-KEM-768) and `EVP_SIGNATURE` (ML-DSA-44/65/87, SLH-DSA-128s/f, SLH-DSA-256s/f) operations directly to AIE2 vector silicon.
2. **OASIS PKCS#11 v3.0 HSM Cryptoki Token (`phoenix_pkcs11_hsm`)**: Implements cryptographic token interface standards (`C_Initialize`, `C_Login`, `C_GenerateKeyPair`, `C_Sign`, `C_Logout`) with hardware key isolation in Tile SRAM and DR10 active zeroization.

---

## 2. Standards Conformance & Interface Architecture

```
       ┌───────────────────────────────────────────────────────────────────────┐
       │             ENTERPRISE APPLICATION / INFRASTRUCTURE LAYER             │
       │   Nginx · Envoy · Apache · OpenSSH · TLS 1.3 · X.509 PKI Authorities │
       └───────────────────────────────────┬───────────────────────────────────┘
                                           │ Standard OpenSSL / PKCS#11 Calls
       ┌───────────────────────────────────▼───────────────────────────────────┐
       │                 PHOENIX NPU PROVIDER & CRYPTOKI LAYER                 │
       │     • phoenix_pqc_provider (OpenSSL 3.x Native C Provider Plugin)     │
       │     • phoenix_pkcs11_hsm   (OASIS PKCS#11 v3.0 Hardware Token Module) │
       └───────────────────────────────────┬───────────────────────────────────┘
                                           │ Zero-Copy XRT DMA ObjectFIFOs
       ════════════════════════════════════╪════════════════════════════════════
                                           │ PHYSICAL AIE2 TILE SILICON
       ┌───────────────────────────────────▼───────────────────────────────────┐
       │   AMD PHOENIX NPU (2D VLIW Vector Matrix: 12 Compute + 4 NOC Tiles)   │
       └───────────────────────────────────────────────────────────────────────┘
```

### 2.1 Supported OpenSSL 3.x Algorithms
- **KEM (`OSSL_OP_KEM`):** `ML-KEM-512`, `ML-KEM-768`, `ML-KEM-1024`, `X25519-ML-KEM-768`, `QKD-ML-KEM-768`.
- **Signatures (`OSSL_OP_SIGNATURE`):** `ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87`, `SLH-DSA-SHAKE-128S`, `SLH-DSA-SHAKE-128F`, `SLH-DSA-SHAKE-256S`, `SLH-DSA-SHAKE-256F`.
- **Key Management (`OSSL_OP_KEYMGMT`):** Hardware-bound `PhoenixPqcKey` objects with zero host key spilling.

### 2.2 PKCS#11 v3.0 Mechanisms
- `CKM_ML_KEM_KEY_PAIR_GEN`, `CKM_ML_KEM_ENCAPSULATE`, `CKM_ML_KEM_DECAPSULATE`
- `CKM_ML_DSA_KEY_PAIR_GEN`, `CKM_ML_DSA`
- `CKM_SLH_DSA_KEY_PAIR_GEN`, `CKM_SLH_DSA`

---

## 3. Academic & Standards Citations

1. **OpenSSL Project (2021):** *OpenSSL 3.0 Provider API Documentation (OSSL_PROVIDER, OSSL_DISPATCH)*. [https://www.openssl.org/docs/man3.0/man7/provider.html](https://www.openssl.org/docs/man3.0/man7/provider.html).
2. **OASIS Standard (2020):** *PKCS #11 Cryptographic Token Interface Base Specification Version 3.0*. OASIS Open.
3. **NIST FIPS PUB 203 (2024):** *Module-Lattice-Based Key-Encapsulation Mechanism Standard*.
4. **NIST FIPS PUB 204 (2024):** *Module-Lattice-Based Digital Signature Standard*.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
