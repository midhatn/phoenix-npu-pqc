# Architectural Decisions Log

## DECISION-20260901-01: DR14 ML-DSA-65 Parameter Sizing and FIPS 204 Conformance

- **Date**: 2026-09-01
- **Author**: Autonomous Engineering Agent (Gemini)
- **Task ID**: `FIX-DR14-FUNCTIONAL-MISMATCH`
- **Scope**: DR14 ML-DSA-65 KeyGen, Sign, and Verify kernels and graphs.

### Context
Execution of `test_dr14_mldsa65_silicon.py` identified parameter discrepancies in the DR14 prototype implementation compared to FIPS 204 (Table 1 and Table 2):
1. The challenge hash $\tilde{c}$ was set to 32 bytes instead of 48 bytes ($2\lambda / 8 = 384\text{ bits} = 48\text{ bytes}$).
2. The hint vector $h$ was allocated 77 bytes instead of 61 bytes ($\omega + k = 55 + 6 = 61\text{ bytes}$).
3. The signature serialization buffer was mismatched ($48 + 3200 + 61 = 3309\text{ bytes}$).

### Decision
1. Updated `sample_in_ball65` in `dr14_mldsa65_internal.hpp` to absorb all 48 bytes of $\tilde{c}$.
2. Corrected `encode_hints65` and `decode_hints65_and_check` to 61-byte layouts with polynomial boundary offsets at `out[55..60]`.
3. Aligned Worker 0, Worker 1, and Worker 2 token offsets across signing and verification pipelines.
4. Added canonical host marshaling for FIPS 204 Alg 7/8 $\mu = \text{SHAKE256}(tr \parallel m, 64)$ when `external_mu == False`.

### Outcome
- 100% bit-exact across all 85 ACVP test cases (25 KeyGen, 30 Sign, 30 Verify) on AMD Phoenix NPU physical silicon.
- PR #13 merged into `main` at commit `f4f16589d0c14c1f2373e95880875644e2d9d342`.
