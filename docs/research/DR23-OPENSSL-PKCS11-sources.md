# DR23 Research and Citation Provenance: OpenSSL 3.x Provider & OASIS PKCS#11 v3.0 HSM Token

## Milestone Deliverable Context
- Deliverable: **DR23 (OpenSSL 3.x Native Provider & OASIS PKCS#11 v3.0 HSM Cryptoki Token)**
- Objective: Provide full software cryptographic provider integration bridging host C/Python applications (OpenSSL 3.x EVP API and OASIS PKCS#11 Cryptoki API) with on-device AMD Phoenix NPU (AIE2 / XDNA1) tile acceleration, with zero CPU fallback and full hardware zeroization.

## Citation Ledger

### Citation 1: OpenSSL 3.x Provider Design and Architecture
- Source Title: OpenSSL 3.0 Provider API Architecture & Design Documentation
- Organization: OpenSSL Management Committee / OpenSSL Software Foundation
- URL: https://www.openssl.org/docs/man3.0/man7/provider.html
- Access Date: 2026-09-01T12:45:00+03:00
- Standards / Release: OpenSSL 3.0 / 3.2 Specification
- Exact Technical Principles:
  - Provider dispatch architecture (`OSSL_DISPATCH`, `OSSL_ALGORITHM`).
  - Standard operations: `OSSL_OP_KEYMGMT` (10), `OSSL_OP_KEYEXCH` (11), `OSSL_OP_SIGNATURE` (12), `OSSL_OP_KEM` (14).
  - Clean separation of provider capabilities, properties query, and hardware-backed key object life cycles.
- Implementation Impact: Implemented `PhoenixPqcProvider` supporting `kem_keygen`, `kem_encapsulate`, `kem_decapsulate`, `signature_keygen`, `signature_sign`, `signature_verify`, and hybrid exchange.

### Citation 2: OASIS PKCS#11 Cryptographic Token Interface Standard
- Source Title: PKCS #11 Cryptographic Token Interface Base Specification Version 3.0
- Organization: OASIS Standard / PKCS #11 Technical Committee
- URL: https://docs.oasis-open.org/pkcs11/pkcs11-base/v3.0/pkcs11-base-v3.0.html
- Access Date: 2026-09-01T12:45:00+03:00
- Standards / Release: OASIS PKCS#11 v3.0 Committee Specification 02
- Exact Technical Principles:
  - Cryptoki slot and token model (`CK_SLOT_INFO`, `CK_TOKEN_INFO`).
  - Session handles and user authentication (`CKU_SO`, `CKU_USER`, `CKF_RW_SESSION`).
  - Standard function dispatch (`C_Initialize`, `C_GetSlotList`, `C_OpenSession`, `C_Login`, `C_GenerateKeyPair`, `C_SignInit`, `C_Sign`, `C_VerifyInit`, `C_Verify`, `C_CloseSession`).
  - Hardware zeroization and session reset behavior.
- Implementation Impact: Implemented `PhoenixPkcs11Hsm` and `PhoenixPkcs11Token` with slot management, user authentication, and hardware-backed key handle binding to AIE2 resident kernels.
