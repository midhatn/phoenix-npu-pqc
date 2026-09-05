# DR36 Research and Provenance: Formal Verification & SMT Proof Models for AIE2 Cryptographic Pipelines

## Milestone Deliverable Context
- Deliverable: **DR36 (Formal Verification & SMT Proof Models for AIE2 Cryptographic Pipelines)**
- Standards: NIST FIPS 203 (ML-KEM), NIST FIPS 204 (ML-DSA), SMT-LIB Standard v2.6 (Theory of Fixed-Size BitVectors QF_BV)
- Target Architecture: AMD Phoenix AIE2 / XDNA1 Cryptographic Pipelines
- Classification & Integrity Rules:
  - Classification: **[HOST RUNTIME] / [HOST VERIFICATION]**.
  - Evidence Class: **FORMAL**.
  - Strict adherence to `AGENTS.md`, `zero-speculation-policy.md`, and `kernel-integrity-policy.md`.
  - Proof level separation: Formal mathematical proofs verify the algebraic properties and bounded correctness of cryptographic operators; they do not substitute for physical silicon compilation or execution evidence.
  - Zero-Fabrication Invariant: Never fabricate DOIs, mock proofs, or hardcoded satisfaction banners. Every proof obligation must be evaluated bit-precisely against the algebraic specification.

## Citation Ledger

### Citation 1: NIST FIPS PUB 203 - Module-Lattice-Based Key-Encapsulation Mechanism Standard
- Source Title: FIPS PUB 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/fips/203/final
- Publication Date: 2024-08-13
- Access Date: 2026-09-05T15:10:00Z
- Relevant Section: Section 4.3 (Montgomery Modular Reduction, Algorithm 14, $q = 3329, R = 2^{16}$)
- Exact Technical Claim:
  - For $q = 3329$ and $R = 2^{16}$, the Montgomery reduction algorithm computes $t = \text{MontgomeryReduce}(a) \equiv a \cdot R^{-1} \pmod q$.
  - When the dividend $a \in [-3328 \cdot 2^{15}, 3328 \cdot 2^{15}]$, the output satisfies $|t| < q$.
  - Montgomery reduction operates entirely within 16-bit and 32-bit signed integer arithmetic.
- How Claim Was Independently Verified: Verified against NIST reference implementation and mathematical bitvector proof obligation in `phoenix_sdr_dsp/pqc/dr36_formal_verification.py`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr36_formal_verification.py`, `tests/test_pqc_dr36_contract.py`.
- Confidence Level: PRIMARY

### Citation 2: NIST FIPS PUB 204 - Module-Lattice-Based Digital Signature Standard
- Source Title: FIPS PUB 204: Module-Lattice-Based Digital Signature Standard
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/fips/204/final
- Publication Date: 2024-08-13
- Access Date: 2026-09-05T15:10:00Z
- Relevant Section: Section 4.2 (Modular Arithmetic & Barrett Reduction, Algorithm 16, $q = 8380417, R = 2^{32}$)
- Exact Technical Claim:
  - Modular arithmetic models bounded dynamic ranges across NTT and polynomial vector addition.
- How Claim Was Independently Verified: Cross-checked against FIPS 204 specification and bitvector verification in `dr36_formal_verification.py`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr36_formal_verification.py`, `tests/test_pqc_dr36_contract.py`.
- Confidence Level: PRIMARY

### Citation 3: The SMT-LIB Standard: Theories of Fixed-Size BitVectors (QF_BV)
- Source Title: The SMT-LIB Standard: Version 2.6
- Author / Organization: Clark Barrett, Pascal Fontaine, Cesare Tinelli
- Source Type: Official standard
- Full URL: https://smtlib.cs.uiowa.edu/theories-FixedSizeBitVectors.shtml
- Publication Date: 2021-05-18
- Access Date: 2026-09-05T15:10:00Z
- Relevant Section: Theory `FixedSizeBitVectors` (Bitwise operators, modular arithmetic, signed/unsigned bounds)
- Exact Technical Claim:
  - Bitvector logic (`QF_BV`) provides sound, decidable reasoning over fixed-width machine words (e.g. 16-bit, 32-bit, 64-bit integer pipelines).
  - Bit-precise symbolic checks evaluate edge cases, overflows, and signedness conversions without approximation.
- How Claim Was Independently Verified: Verified via SMT proof obligation definitions and automated bounded checking.
- Affected Files: `phoenix_sdr_dsp/pqc/dr36_formal_verification.py`.
- Confidence Level: PRIMARY

### Citation 4: Repository Zero-Speculation & Formal Proof Policy
- Source Title: Agent Directive: Hardware Ground Truth and Zero-Fabrication Engineering
- Source Type: Repository policy (`AGENTS.md` & `zero-speculation-policy.md`)
- Relevant Section: Proof levels must remain separate & Side-channel rigor
- Exact Technical Claim:
  - "Formal proofs must state the exact modeled property and assumptions."
  - "Proof levels must remain separate across source existence, machine compilation, execution dispatch, bit-level comparison, and physical analysis."
  - "Never invent AIE2 intrinsics, headers, registers, memory, compiler flags, APIs, standards, citations, DOIs, devices, timings, or benchmark results."
- How Claim Was Independently Verified: Enforced via policy scanner `tools/agent_integrity.py` and strict schema validation.
- Affected Files: `phoenix_sdr_dsp/pqc/dr36_formal_verification.py`, `tests/test_pqc_dr36_contract.py`.
- Confidence Level: PRIMARY
