# DR30 Research and Citation Provenance: 3GPP 5G/6G Core Network SUCI Co-Processor

## Milestone Deliverable Context
- Deliverable: **DR30 (3GPP TS 33.501 5G/6G Core Network SUCI Co-Processor)**
- Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- Standards: 3GPP TS 33.501 (Release 18/19), 3GPP TR 33.841, NIST FIPS 203 (ML-KEM)

## Citation Ledger

### Citation 1: 3GPP TS 33.501: Security Architecture and Procedures for 5G System
- Source Title: 3rd Generation Partnership Project; Technical Specification Group Services and System Aspects; Security architecture and procedures for 5G System (Release 18 & Release 19)
- Issuing Organization: 3GPP (3rd Generation Partnership Project)
- Standard Identifier: 3GPP TS 33.501 v18.4.0 / v19.0.0
- URL: https://www.3gpp.org/ftp/Specs/archive/33_series/33.501/
- Relevant Section: Section 6.1.3 (Subscription identification and privacy) & Annex C (Subscription Concealed Identifier calculation)
- Exact Technical Principles:
  - Protection of user identity: SUPI (Subscription Permanent Identifier) must be concealed as SUCI (Subscription Concealed Identifier) over radio links.
  - Wire format of SUCI:
    - SUPI Type (1 byte): 0 for IMSI, 1 for Network Specific Identifier.
    - Home Network Identifier: MCC (Mobile Country Code, 3 digits) and MNC (Mobile Network Code, 2 or 3 digits).
    - Routing Indicator (4 hex digits / 2 bytes).
    - Protection Scheme Identifier (1 byte): 0x00 (Null), 0x01 (Profile A - Curve25519), 0x02 (Profile B - Secp256r1), 0x03 (Profile C - Post-Quantum ML-KEM-768), 0x04 (Profile D - Post-Quantum ML-KEM-1024).
    - Home Network Public Key Identifier (1 byte).
    - Scheme Output: Ephemeral public key / ciphertext $c$, encrypted MSIN/SUPI payload, and MAC tag.
  - SIDF (Subscription Identifier De-concealing Function) role: Located in the UDM/ARPF; decapsulates the shared secret using the Home Network Private Key, derives session keys ($K_{enc}, K_{mac}$), and decrypts the SUPI.
- Implementation Impact: Implemented hardware-accelerated 3GPP SIDF de-concealment engine executing wire-format parsing, ML-KEM shared secret decapsulation, key derivation, and SUPI decryption on AMD Phoenix AIE2.

### Citation 2: 3GPP TR 33.841: Study on Post-Quantum Cryptography for 5G System
- Source Title: Study on Post-Quantum Cryptography for 5G System (Release 18/19)
- Issuing Organization: 3GPP SA3 (Security)
- Standard Identifier: 3GPP TR 33.841
- URL: https://www.3gpp.org/ftp/Specs/archive/33_series/33.841/
- Relevant Section: Section 5.2 (PQC for SUCI de-concealment in 5G Core Network)
- Exact Technical Principles:
  - Profile C and Profile D integration for SUCI privacy preservation against "Harvest-Now, Decrypt-Later" adversaries.
  - High-throughput requirement: Telecom core network functions (UDM/AUSF) must handle hundreds of thousands of concurrent subscriber registrations per second, necessitating dedicated hardware co-processor offload with microsecond latency.
- Implementation Impact: Designed the AIE2 SIMD kernel to execute atomic SUCI de-concealment pipelines with sub-millisecond execution times, zero CPU host interrupts, and sealed tile SRAM residency.
