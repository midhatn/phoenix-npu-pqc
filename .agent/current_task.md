# Current Task

## Task

`FIX-DR15-FUNCTIONAL-MISMATCH`: Debug and resolve observed functional mismatches in DR15 ML-DSA-87 across canonical silicon gates (KeyGen, Sign, Verify).

## Status

`IN_PROGRESS` (Active Milestone: DR15 ML-DSA-87).
1. DR2d ML-KEM-512 K-PKE KeyGen: `COMPLETED` (25/25 vectors PASS, merged in PR #10, protected evidence archive at `C:\Projects\phoenix-validation-evidence\dr2d-a0405851-20260901`).
2. DR14 ML-DSA-65: `COMPLETED` (85/85 vectors PASS — 25 KeyGen, 30 Sign, 30 Verify — merged in PR #13 at commit `f4f1658`).
3. DR15 ML-DSA-87: `READY` for parameter audit (FIPS 204 ML-DSA-87 parameters: $k=8, l=7, \tau=60, \lambda=256, \gamma_1=2^{19}, \gamma_2=(q-1)/32=261888, \beta=120, \omega=75, \tilde{c}=64\text{ B}, h=83\text{ B}, z=4480\text{ B}$, total signature size: $64 + 4480 + 83 = 4627\text{ bytes}$).

## Next Action
Create milestone branch `fix/dr15-mldsa87-correctness`, audit C++ kernels and graph token sizes, run mathematical transliteration checks, and execute physical silicon suite `tests/pqc_device_resident/test_dr15_mldsa87_silicon.py`.
