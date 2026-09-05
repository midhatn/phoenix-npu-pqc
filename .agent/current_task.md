# Current Task

## Task

AUDIT_MATHEMATICS_AND_BASELINE_EVIDENCE_MATRIX: Perform an exhaustive review and audit of all documentation across `phoenix-npu-pqc`, correcting all mathematical errors, accounting inconsistencies, and outdated historical baseline data.

## Status

COMPLETED and MERGED in PR #40.
- Final Default Branch (`main`): `a292b5a032076b2249ac73f44404660e3873ce17`
- Working Tree: Clean
- Audited Scope:
  - `README.md`: Reconciled Module 2 (ML-KEM: 225 cases), Module 4 (Lifecycle: 134 cases), and Module 5 (Hybrid QKD: 100 cases). Corrected total runtime sum to exact mathematical sum of detail rows (31.14s) across 24 registered gates (857 test cases). Clarified Barrett reduction remainder bounds $r \in [0, 2q)$ (maximum 3332) in Section 5.2.
  - `docs/BENCHMARKS.md`: Reconciled Section 2 detail rows to match canonical gate IDs and test case counts; added missing Gate 23 (DR27: 21 cases, 1.23s, 58.6 ms avg). Verified exact mathematical sum equals 857 test cases in 31.14s with 36.3 ms average op latency.
  - `docs/PQC_FINAL_SILICON_REPORT_20260829.md`: Reconciled FIPS 203 (225 cases) and Lifecycle (134 cases) module counts, replaced obsolete "3 functional fail gates" with canonical status, and updated runner references.
  - `docs/PQC_CITATION_AND_MATHEMATICS_AUDIT_20260828.md`: Corrected sign in Montgomery reduction formula from $+$ to $-$, fixed modular inverse precision label ($q^{-1} \equiv 62209 \pmod{2^{16}}$ for ML-KEM vs $\pmod{2^{32}}$ for ML-DSA), and reconciled module counts.
  - `docs/PQC_ROADMAP.md`: Reconciled Evaluation Scope to reflect all 19 core gates matching reference oracles bit-exactly with 0 functional mismatches in registered baseline.
  - `docs/PQC_AND_QKD_ROADMAP.md`: Reconciled badge to "24 Gates Bit-Exact" and unverified gates note to 24 registered gates.
  - `docs/PQC_DEVICE_RESIDENCY_ROADMAP.md`: Removed unannotated physical silicon and certified claims in Current State section.
  - `docs/RELEASE_NOTES_v1.1.0.md` & `docs/v1.1.0_REPO_WIDE_ASSESSMENT_REPORT.md`: Reconciled module counts to exact figures, removed superlative unannotated claims, and added historical claim provenance markers.
- Verification Results:
  - `python tools/verify_agent_change.py` passed with 0 blocking, 0 warnings.
  - `python -m unittest discover -s tests/policy -v` passed (125/125 tests OK).
  - `python -m unittest tests/test_markdown_math_contract.py tests/test_release_materials_contract.py -v` passed (10/10 tests OK).
  - `python run_all_pqc_tests.py` passed across all 42 modules.

## Next Action

Maintain clean verified state and support customer offline demonstration of authentic core primitives.
