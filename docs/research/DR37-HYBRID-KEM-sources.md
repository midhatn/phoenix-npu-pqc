# DR37 Research and Provenance: Dual-Scheme Hybrid KEM Engine (X25519 + ML-KEM-768)

## Milestone Deliverable Context
- Deliverable: **DR37 (Dual-Scheme Hybrid Classical / Quantum-Safe KEM Engine on AMD Phoenix AIE2)**
- Standards: ETSI TS 103 744, BSI TR-02102-1, IETF RFC 9180 (HPKE), NIST SP 800-56C Rev. 2
- Target Architecture: AMD Phoenix AIE2 / XDNA1 (AIE2 Vector & Keccak / PRF Tiles)
- Classification & Integrity Rules:
  - Kernel Execution: **[ON-TILE SILICON]** for AIE2 hardware dispatch.
  - Host Harness & Verification: **[HOST RUNTIME]** with parent reference oracle comparison.
  - Anti-Fabrication Invariant: The combiner must implement the exact normative dual-PRF / HKDF-Extract-and-Expand construction specified in ETSI TS 103 744 and NIST SP 800-56C.
  - No fake XOR or arbitrary magic constants represented as cryptographic derivation.
  - Fail-closed handling for degenerate classical public keys (e.g. low-order Curve25519 points) or zeroed shared secrets.

## Citation Ledger

### Citation 1: ETSI TS 103 744 - Quantum-Safe Hybrid Key Exchanges
- Source Title: ETSI TS 103 744 V1.1.1: CYBER; Quantum-Safe Hybrid Key Exchanges
- Author / Organization: European Telecommunications Standards Institute (ETSI)
- Source Type: Normative standard
- Full URL: https://www.etsi.org/deliver/etsi_ts/103700_103799/103744/01.01.01_60/ts_103744v010101p.pdf
- Publication Date: 2020-12-01
- Access Date: 2026-09-05T15:15:00Z
- Relevant Section: Section 5.2 (Dual-PRF Key Combiner Construction & Input Keying Material Formulation)
- Exact Technical Claim:
  - The hybrid key combiner accepts shared secrets $ss_c$ (classical) and $ss_{pqc}$ (quantum-safe) along with session transcripts and ciphertexts.
  - Input keying material is formed as $\text{IKM} = ss_c \parallel ss_{pqc}$.
  - The final shared secret is extracted and expanded using a dual-PRF structure that remains secure if either the classical or the quantum-safe component remains uncompromised.
- How Claim Was Independently Verified: Verified against ETSI TS 103 744 Algorithm 1 and implemented in `dr37_hybrid_kem_internal.hpp`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr37_hybrid_kem_abi.py`, `phoenix_sdr_dsp/pqc/kernels/dr37_hybrid_kem_internal.hpp`.
- Confidence Level: PRIMARY

### Citation 2: BSI Technical Guideline TR-02102-1: Cryptographic Mechanisms for TLS 1.3
- Source Title: BSI TR-02102-1: Cryptographic Mechanisms: Recommendations and Key Lengths
- Author / Organization: Federal Office for Information Security (BSI Germany)
- Source Type: Government technical guideline
- Full URL: https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Publications/TechGuidelines/TG02102/BSI-TR-02102-1.pdf
- Publication Date: 2024-03-22
- Access Date: 2026-09-05T15:15:00Z
- Relevant Section: Section 3.4 (Hybrid Key Exchange with ML-KEM-768 and Curve25519)
- Exact Technical Claim:
  - Recommends the combination of ML-KEM-768 with ECDHE (X25519) for post-quantum migration.
  - Mandates explicit validation to prevent all-zero or degenerate classical shared secrets from compromising the combiner.
- How Claim Was Independently Verified: Implemented in `dr37_hybrid_kem_internal.hpp` with policy enforcement checks rejecting degenerate keys.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr37_hybrid_kem_internal.hpp`, `phoenix_sdr_dsp/pqc/dr37_hybrid_kem_abi.py`.
- Confidence Level: PRIMARY

### Citation 3: IETF RFC 9180 - Hybrid Public Key Encryption (HPKE)
- Source Title: RFC 9180: Hybrid Public Key Encryption
- Author / Organization: Internet Engineering Task Force (IETF) / R. Barnes, K. Bhargavan, B. Lipp, C. Wood
- Source Type: Normative standard
- Full URL: https://www.rfc-editor.org/rfc/rfc9180.html
- Publication Date: 2022-02-01
- Access Date: 2026-09-05T15:15:00Z
- Relevant Section: Section 4 (Key Encapsulation Mechanism Interface) & Section 5.1 (Key Derivation Function)
- Exact Technical Claim:
  - Formulates standard KEM interfaces `Encap` and `Decap` returning `(shared_secret, ciphertext)`.
  - Defines `LabeledExtract` and `LabeledExpand` over HKDF with contextual protocol label strings.
- How Claim Was Independently Verified: Verified against RFC 9180 test vectors and implemented in `dr37_hybrid_kem_internal.hpp`.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr37_hybrid_kem_internal.hpp`, `tests/test_pqc_dr37_contract.py`.
- Confidence Level: PRIMARY

### Citation 4: NIST SP 800-56C Rev. 2 - Recommendation for Key-Derivation Methods in Key-Establishment Schemes
- Source Title: NIST Special Publication 800-56C Revision 2: Recommendation for Key-Derivation Methods
- Author / Organization: National Institute of Standards and Technology (NIST)
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/56/c/r2/final
- Publication Date: 2020-08-01
- Access Date: 2026-09-05T15:15:00Z
- Relevant Section: Section 4 (Two-Step Key Derivation Procedure: Extraction then Expansion)
- Exact Technical Claim:
  - Two-step key derivation procedure: Step 1 computes pseudo-random key $PRK = \text{HMAC}(salt, IKM)$; Step 2 computes derived keys $OKM = \text{Expand}(PRK, info, L)$.
- How Claim Was Independently Verified: Implemented in AIE2 service kernel with bit-exact reference oracle verification.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr37_hybrid_kem_internal.hpp`, `phoenix_sdr_dsp/pqc/dr37_hybrid_kem_abi.py`.
- Confidence Level: PRIMARY
