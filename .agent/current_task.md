# Current Task

## Task

CUSTOMER_READINESS_AUDIT_AND_RELEASE_FREEZE: Consolidate cryptographic remediation, NPU-only customer acceptance, clean-clone onboarding verification, and release freeze for Phoenix NPU PQC on AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS).

## Status

FREEZE_AND_HANDOFF_COMPLETE.
- Final Default Branch (`main`): `7283b567e39383814e4ac4f92be43535cc5017d1`
- Working Tree: Clean
- Operational Scope:
  - Authentic Core Primitives (FIPS 202, FIPS 203, FIPS 204, ETSI QKD 014 / SP 800-56C): Validated 100% bit-exact against official ACVP KATs on target silicon.
  - Quarantined Deliverables: Ten (10) late deliverables placed in mandatory quarantine (`BLOCKED_THREE_STRIKES`) due to critical semantic shortcuts: DR21, DR22, DR30, DR31, DR34, DR36, DR38, DR39, DR41, DR42.
  - Excluded Deliverables: DR43 (Constitutional exclusion), DR20 (Specification blocked).
  - Host-Only Deliverables: DR32 (X.509/TLS), DR35 (Telemetry Harvester) (`HOST_VERIFIED_ONLY`).
- Offline Customer Demonstration Suite:
  - Orchestrator: `customer_demo/run_customer_npu_pqc_demo.ps1 -Offline -StrictNpu`
  - Preflight: `customer_demo/verify_offline_package.ps1`
  - Rehearsals: Both clean rehearsals executed and preserved with zero CPU fallback.
- Customer Readiness Verdict: `CUSTOMER READY: NO-GO` (due to quarantined extension milestones and open driver-level dispatch trace corroboration).

## Next Action

Execute driver-level hardware trace verifier (`tools/verify_npu_dispatch.py`) to close `PHYSICAL-DISPATCH-CORROBORATION` and formally bound customer demonstration contracts strictly to verified core primitives.
