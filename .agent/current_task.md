# Current Task

## Task

`POLICY-MULTILANG-INTEGRITY`: Implement repository-wide multi-language integrity enforcement and claim-level provenance validation on bounded branch `policy/multilang-integrity`.

## Status

`COMPLETED` (Tasks 1 through 4 Finished).
1. `POLICY-MULTILANG-COVERAGE`: Extended `tools/agent_integrity.py` and `tools/verify_agent_change.py` to scan all 15 supported repository extensions (`.py`, `.c`, `.cc`, `.cpp`, `.h`, `.hpp`, `.mlir`, `.ps1`, `.sh`, `.cmake`, `CMakeLists.txt`, `.yml`, `.yaml`, `.json`, `.md`) with language-specific rules (`CPP*`, `SH*`, `SEC*`, `DOC*`, `FMT*`, `PATH*`, `MLIR*`, `CMAKE*`).
2. `POLICY-DOC-CLAIM-AUDIT`: Replaced document-wide suppression with strict claim-level provenance parsing (`[CLAIM-PROVENANCE: status=...; evidence=...; commit=...; classification=...]`), validated line-by-line single-claim adjacency, and audited all repository documentation lines.
3. `CI-REQUIRED-CHECK-TRIGGERS`: Restored `.github/workflows/ci.yml` defining the exact 5 branch protection jobs (`Lint Python`, `Validate metadata`, `Host-safe PQC tests`, `Verify protected DR2 evidence`, `Check Markdown links`) triggering across all PRs.
4. `POLICY-SCANNER-SELF-PROTECTION`: Validated single-self-exclusion (`EXCLUDED_POLICY_PATHS == {Path("tools/agent_integrity.py")}`), non-mutating read-only scanner behavior, path traversal guards (`PATH001`), and comprehensive adversarial test coverage (47 unit tests passing including all 13 claim-level provenance regression tests).

## Remaining Tasks in Queue
- `ARTIFACT-CACHE-PROVENANCE` (READY)
- `SUPPLY-CHAIN-AND-LICENSE-AUDIT` (READY)
- `PHYSICAL-DISPATCH-CORROBORATION` (BLOCKED)
- `FIX-DR2D-FUNCTIONAL-MISMATCH` (READY - reserved for dedicated repair branch)
- `FIX-DR14-FUNCTIONAL-MISMATCH` (READY - reserved for dedicated repair branch)
- `FIX-DR15-FUNCTIONAL-MISMATCH` (READY - reserved for dedicated repair branch)
