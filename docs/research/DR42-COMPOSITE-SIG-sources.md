# Research Ledger: Milestone DR42 - Composite & Dual-Signature Sovereign Standard Engine

## Task Information
- **Task ID**: `DR42-COMPOSITE-SIG`
- **Milestone**: DR42 (ANSSI Composite & Dual-Signature Sovereign Standard Engine)
- **Target Hardware**: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- **Governing Directives**: `AGENTS.md`, `kernel-integrity-policy.md`, `autonomous-execution-constitution.md`, `zero-speculation-policy.md`
- **Date**: 2026-09-05

---

## Authoritative Standards and Normative Citations

### Source 1: ANSSI Views on the Post-Quantum Cryptography Transition
- **Title**: ANSSI Views on the Post-Quantum Cryptography Transition
- **Author/Organization**: Agence nationale de la sécurité des systèmes d'information (ANSSI, French National Cybersecurity Agency)
- **Source Type**: Normative Position Paper / Government Guidance
- **Full URL**: `https://cyber.gouv.fr/publications/anssi-views-post-quantum-cryptography-transition`
- **Publication Date**: 2022-01
- **Access Date**: 2026-09-05T19:45:00Z
- **Applicable Version**: Scientific Position Paper (Version 1.1)
- **Relevant Section**: Section 3 ("The Hybrid Approach"), Subsection 3.2 ("Hybrid Schemes Definition")
- **Exact Technical Claim**:
  During the quantum transition period, hybrid mechanisms that combine an established classical algorithm (such as ECDSA or Ed25519) with a recognized post-quantum algorithm (such as ML-DSA) are mandatory for sovereign compliance. The dual-signature verification must be conjunctive: a message is accepted if and only if both the classical verification and the post-quantum verification succeed independently. If either verification fails, the composite signature must be rejected immediately (fail-closed).
- **Independent Verification Method**:
  Verified by implementing atomic boolean conjunction in AIE2 service kernel where failure of either component terminates verification with an explicit non-zero error code.
- **Affected Repository Files**:
  - `phoenix_sdr_dsp/pqc/dr42_composite_sig_abi.py`
  - `phoenix_sdr_dsp/pqc/dr42_composite_sig_graph.py`
  - `phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_service.cc`
  - `tests/pqc_device_resident/test_dr42_composite_sig_silicon.py`
- **Confidence Level**: `PRIMARY`

---

### Source 2: BSI Technical Guideline TR-02102-1
- **Title**: BSI TR-02102-1: Cryptographic Mechanisms: Recommendations and Key Lengths
- **Author/Organization**: Federal Office for Information Security, Germany (Bundesamt für Sicherheit in der Informationstechnik - BSI)
- **Source Type**: Normative Technical Guideline
- **Full URL**: `https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Publications/TechGuidelines/TG02102/BSI-TR-02102-1.pdf`
- **Publication Date**: 2024-02
- **Access Date**: 2026-09-05T19:45:00Z
- **Applicable Version**: Version 2024-01
- **Relevant Section**: Section 5.3 ("Hybrid Quantum-Resistant Digital Signatures")
- **Exact Technical Claim**:
  Recommends migration using dual classical and post-quantum keys, specifically combining elliptic curves with module-lattice signatures. Security requires that compromise of either mathematical assumption does not compromise the authenticity of verified documents.
- **Independent Verification Method**:
  Implemented in compound key descriptors and verified under adversarial test vectors where one key or signature component is mutated.
- **Affected Repository Files**:
  - `phoenix_sdr_dsp/pqc/dr42_composite_sig_abi.py`
  - `tests/test_pqc_dr42_contract.py`
- **Confidence Level**: `PRIMARY`

---

### Source 3: IETF LAMPS Composite Signatures Internet-Draft
- **Title**: Composite Signatures For Use In Internet PKI
- **Author/Organization**: M. Ounsworth, J. Gray, M. Pala, J. Klaußner (IETF LAMPS WG)
- **Source Type**: Normative Protocol Specification (Internet-Draft)
- **Full URL**: `https://datatracker.ietf.org/doc/draft-ietf-lamps-pq-composite-sigs/`
- **Publication Date**: 2024-03-04
- **Access Date**: 2026-09-05T19:45:00Z
- **Applicable Version**: draft-ietf-lamps-pq-composite-sigs-02
- **Relevant Section**: Section 3 ("Composite Signature Generation and Verification"), Section 4 ("Composite Combinations")
- **Exact Technical Claim**:
  Defines composite combinations:
  - `id-MLDSA44-Ed25519-SHA512` (NIST Security Category 2)
  - `id-MLDSA65-ECDSA-P384-SHA384` (NIST Security Category 3)
  - `id-MLDSA87-ECDSA-P521-SHA512` (NIST Security Category 5)
  A composite signature data structure encapsulates both component signatures. Verification requires:
  1. Parse component keys and signatures.
  2. Compute composite domain-separated pre-hash over message payload.
  3. Verify traditional component against message digest.
  4. Verify post-quantum component against message digest.
  5. Conjunction: both must return success.
- **Independent Verification Method**:
  Implemented in `dr42_composite_sig_abi.py` and `dr42_composite_sig_service.cc` with exact parsing and verification conjunction.
- **Affected Repository Files**:
  - `phoenix_sdr_dsp/pqc/dr42_composite_sig_abi.py`
  - `phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_service.cc`
  - `tests/test_pqc_dr42_contract.py`
  - `tests/pqc_device_resident/test_dr42_composite_sig_silicon.py`
- **Confidence Level**: `PRIMARY`

---

### Source 4: NIST FIPS 204: Module-Lattice-Based Digital Signature Standard
- **Title**: FIPS 204: Module-Lattice-Based Digital Signature Standard
- **Author/Organization**: National Institute of Standards and Technology (NIST)
- **Source Type**: Normative Federal Information Processing Standard
- **Full URL**: `https://csrc.nist.gov/pubs/fips/204/final`
- **Publication Date**: 2024-08-13
- **Access Date**: 2026-09-05T19:45:00Z
- **Applicable Version**: FIPS 204 Final
- **Relevant Section**: Section 5 ("ML-DSA Algorithms"), Algorithm 8 (`ML-DSA.Verify`)
- **Exact Technical Claim**:
  Verification computes polynomial norm bound checks $\|\mathbf{z}\|_\infty < \gamma_1 - \beta$, hint checks, and verifies challenge hash $c = H(\mu \parallel w_1)$.
- **Independent Verification Method**:
  On-tile verification math and modular reduction using AIE2 vector compute primitives verified bit-exact against independent Python reference.
- **Affected Repository Files**:
  - `phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_internal.hpp`
  - `phoenix_sdr_dsp/pqc/kernels/dr42_composite_sig_service.cc`
- **Confidence Level**: `PRIMARY`

---

### Source 5: RFC 8032: Edwards-Curve Digital Signature Algorithm (Ed25519)
- **Title**: RFC 8032: Edwards-Curve Digital Signature Algorithm (Ed25519)
- **Author/Organization**: S. Josefsson, I. Liusvaara (IETF)
- **Source Type**: Normative RFC Standard
- **Full URL**: `https://www.rfc-editor.org/rfc/rfc8032`
- **Publication Date**: 2017-01
- **Access Date**: 2026-09-05T19:45:00Z
- **Applicable Version**: RFC 8032
- **Relevant Section**: Section 5.1 ("Ed25519")
- **Exact Technical Claim**:
  Ed25519 keys are 32 bytes, signatures are 64 bytes $(R \parallel S)$. Verification checks $8 S B = 8 R + 8 H(R, A, M) A$ over Curve25519.
- **Independent Verification Method**:
  Verified in reference oracle and test vectors with independent cryptography library (`cryptography` / `ed25519`).
- **Affected Repository Files**:
  - `phoenix_sdr_dsp/pqc/dr42_composite_sig_abi.py`
  - `tests/test_pqc_dr42_contract.py`
- **Confidence Level**: `PRIMARY`
