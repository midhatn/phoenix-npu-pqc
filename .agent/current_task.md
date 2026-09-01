# Current Task

## Task

`DR25-HIGHER-ORDER-MASKING`: Implement Higher-Order Masking & On-Chip Local PRNG Entropy Expansion on AMD Phoenix AIE2 (XDNA1).

## Status

`IN_PROGRESS` (Milestone DR25).
- Prior Milestones:
  1. `DR2d` (ML-KEM-512 K-PKE KeyGen): `COMPLETED` (25/25 vectors PASS, PR #10).
  2. `DR14` (ML-DSA-65 KeyGen, Sign, Verify): `COMPLETED` (85/85 vectors PASS, PR #13).
  3. `DR15` (ML-DSA-87 KeyGen, Sign, Verify): `COMPLETED` (85/85 vectors PASS, PR #15).
  4. `DR16-DR19, DR27` (Extension Gates Framed Evidence Migration): `COMPLETED` (121/121 cases PASS, PR #16).
  5. `DR21` (NIST FIPS 205 SLH-DSA KeyGen, Sign, Verify): `COMPLETED` (30/30 cases PASS, PR #17).
  6. `DR22` (NIST FIPS 206 FN-DSA KeyGen, Sign, Verify): `COMPLETED` (30/30 cases PASS, PR #18).
  7. `DR23` (OpenSSL 3.x Provider & OASIS PKCS#11 HSM): `COMPLETED` (25/25 cases PASS, PR #19).
  8. `DR24` (RFC 9370 Multi-KEM IPsec & WireGuard Acceleration): `COMPLETED` (25/25 cases PASS, PR #20).
  9. Native Silicon Validation Baseline: 28 native deliverables with structured framed evidence on AMD Phoenix NPU physical silicon (967/967 test cases bit-exact matching).

## Next Action

Research higher-order polynomial masking schemes (1st- and 2nd-order polynomial blinding) and on-tile FIPS 202 SHAKE-128 PRNG stream generation for continuous share refreshes; create research ledger `docs/research/DR25-MASKING-PRNG-sources.md`.
