# DR2c Physical Validation Follow-up Handoff

## Scope

This narrow follow-up modifies only:

- `docs/PQC_DR2C_SILICON_VALIDATION_PENDING.md`
- `tests/test_pqc_dr2c_contract.py`

It converts the DR2c pending checklist into a dated, bounded physical-validation
record and anchors that record in the static contract. It does not modify
production code, the canonical runner, publication mathematics, or any prior
milestone.

## Recorded physical result

On 2026-08-17, the corrected two-host-input DR2c graph executed on Phoenix with
backend `dr2c-mlkem512-keygen-row:silicon`. The first gate completed all 11
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr2c_physical_validation_handoff_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
named frozen-corpus cases with `TOTAL 11/11 PASS`, exit 0. Calling
`_run_native_gate()` twice in the same Python process produced two `TOTAL 11/11
PASS` results, 22/22 aggregate, exit 0.

The physical record preserves the supplied JIT-cache basename; packaged-artifact
timestamp, sizes, PDI and partition metadata; HOST/SRAM memory-topology
presence; per-worker ELF file and section sizes; linker program/data regions
and stack reservations; exactly four logical depth-two FIFOs across two cores;
placed buffer tile/bank/address pairs; the three exact shim DMA flows; and the
three shim allocations. Operations-per-cycle is explicitly described as
metadata only, not a measured performance result.

## Claim boundary

The physical result is only for one terminal ML-KEM-512 `t_hat` row under the 11-case native corpus. It does not claim complete K-PKE.KeyGen or ML-KEM: `G(d || k)`, both-row scheduling, key serialization, and lifecycle zeroization remain outside DR2c. It also excludes performance, constant-time, secure-zeroization, side-channel, security-hardening, CMVP, and certification claims.

## Local follow-up validation

The corrected add-only base patch and this follow-up were applied in an isolated
checkout before validation.

- Focused host command:

  ```text
  python -m unittest \
    tests.pqc_device_resident.test_dr2c_mlkem512_keygen_row \
    tests.test_pqc_dr2c_contract
  ```

  Result: `Ran 14 tests` — `OK`. This includes the strict C++17 production
  harness compilation (`-std=c++17 -Wall -Wextra -Werror -pedantic`).

- Ruff command over all six DR2c Python/test modules: passed (`All checks
  passed!`).
- `git diff --check` over the combined base-plus-follow-up checkout: passed.
- The native-only command below returned exit 2 with
  `Backend: dr2c-mlkem512-keygen-row:unavailable`, confirming unavailable is
  fail-closed and no host fallback ran. This local machine did not perform the
  recorded physical run.
- The generated follow-up patch contains exactly the two paths listed in
  **Scope**. The canonical `run_all_silicon_tests.py` content is also
  statically asserted unchanged by the DR2c contract test.

## Native-only Phoenix command

```powershell
py .\tests\pqc_device_resident\test_dr2c_mlkem512_keygen_row_silicon.py
```

A physical rerun is a pass only when it reports the silicon backend and the
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr2c_physical_validation_handoff_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
anchored `TOTAL 11/11 PASS`; exit 2 is unavailable, not a pass.

## Deliverables

- Follow-up patch: `PQC_DR2C_PHYSICAL_VALIDATION_FOLLOWUP_20260817.patch`
- Handoff: `PQC_DR2C_PHYSICAL_VALIDATION_HANDOFF_20260817.md`
