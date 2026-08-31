# Current Task

## Task

`DR14-MIGRATE`: Bounded DR14 ML-DSA-65 (KeyGen, Sign, Verify) structured evidence migration and parent oracle verification.

## Status

`COMPLETED` (Bounded DR14 implementation & parent-side NIST ACVP oracle verification completed).
- Structured framed evidence emission: Implemented (`<<<PQC_SILICON_GATE_RESULT_V1>>>`).
- Parent-side buffer oracle verification: Implemented (85 official NIST ACVP ML-DSA-65 cases evaluated; 72 pass, 13 silicon failures verified bit-exact against reference vectors).
- Redirection exclusion: `XCL_EMULATION_MODE` and `XRT_INI_PATH` explicitly rejected fail-closed.
- Physical evidence state: `FAIL` (exit 1, success=False, cases_passed=0, cases_failed=13, 13 oracle mismatches on physical device).
- Hardware ground truth: Truthfully classified as failing physical gate under zero-speculation policy.







