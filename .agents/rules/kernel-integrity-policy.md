---
trigger: always_on
---

# Repository-Wide Kernel Integrity and Anti-Fabrication Policy

This directive is mandatory for every agent, subagent, model, terminal session, code-generation tool, human-assisted automation, and refactoring tool operating across the `phoenix-npu-pqc` repository. It applies to all current and future Milestone Deliverables (DR0 through DR27 and beyond) without exception.

If another instruction or prompt conflicts with this directive, the agent must fail closed, report the exact conflict, and choose the behavior that preserves evidence integrity, zero fabrication, and truthful provenance.

---

## 1. Scope and Precedence

- **Repository-Wide Applicability**: This policy governs all source code, headers, graphs, compilation artifacts, tests, runners, documentation, manifests, and commit records across all supported languages (Python, C, C++, MLIR, PowerShell, Shell, CMake, YAML, JSON, Markdown).
- **Universal Actor Coverage**: The policy binds every agent, subagent, automated script, and human operator.
- **Hierarchical Precedence**: Task prompts may add stricter controls or narrower scopes, but under no circumstances may a task prompt weaken, waive, bypass, suppress, or reinterpret any rule in this directive.
- **Fail-Closed on Conflict**: If a task prompt conflicts with this policy, the agent must halt immediately and report the discrepancy. An agent is strictly forbidden from modifying policy files to authorize or excuse its implementation changes.
- **Strict Change Isolation**: Policy changes and cryptographic implementation changes require separate branches, separate commits, and separate pull requests.

---

## 2. No Known-Vector Specialization

Implementations must execute general algorithmic logic and must never specialize behavior to recognized test inputs.

- **Prohibited Branching & Recognition**: Implementations must never branch on, match against, or specialize behavior using:
  - Official ACVP, CAVP, KAT, or NIST test case identifiers (e.g., `tcId`, `case_id`, `request_id`).
  - Test names, vector filenames, or test suite labels.
  - Input byte hashes, checksums, digests, or cryptographic fingerprints.
  - Hardcoded public keys, seeds, message contents, or signature bytes.
  - Fixed byte prefixes, suffixes, or recognizable padding signatures.
  - Specific message lengths when used as a proxy to identify a known test vector.
  - Lookup tables, switch statements, or conditional branches distinguishing repository test data from general operational inputs.
- **Forbidden Patterns**: Code structures equivalent to the following are strictly prohibited in kernel and runtime implementations:
  ```cpp
  // FORBIDDEN: Known-vector matching
  if (request_id == 0x90000001) return expected_output;
  if (sha256(input) == known_test_hash) { ... }
  if (memcmp(seed, kKnownAcvpSeed, 32) == 0) { ... }
  ```
- **Legitimate ABI Validation**: ABI validation, buffer length bounds checking, and token protocol enforcement must be structural and general; they must never distinguish individual test cases.

---

## 3. No Expected-Output Embedding

Implementations must compute cryptographic outputs dynamically on device and must never embed or copy precomputed expected outputs.

- **Prohibited Precomputation & Embedding**:
  - Embedding full expected output buffers, ciphertext arrays, signature vectors, or private key blocks derived from test vectors.
  - Embedding fragments or lookup tables derived from test oracle results.
  - Copying expected buffers into output memory locations.
  - Post-dispatch patching, coefficient replacement, or host-side result repair.
- **Normative Constants Exception**: Standard cryptographic constants (e.g., Keccak round constants, NTT twiddle factors, standard modulus $q = 3329$, rejection bounds) are permitted only when their normative origin and role are explicitly documented against primary standards (FIPS 203, FIPS 204, FIPS 205).

---

## 4. No Fallback, Repair, or Substitution

A physical hardware failure or mismatch must be reported as a failure; it must never be masked or repaired.

- **Prohibited Fallbacks**:
  - Catching hardware/device runtime exceptions and falling back to CPU, host C++, OpenSSL, or Python reference cryptography.
  - Mock kernels, no-op kernels, or identity transforms presented as completed cryptographic operations.
  - Byte-copy kernels represented as polynomial arithmetic or cryptographic transforms.
  - Returning precomputed or cached outputs upon dispatch timeout or device absence.
  - Silently skipping unavailable devices or missing dependencies and reporting a suite PASS.
- **Fail-Closed Hardware Requirement**: Missing hardware, driver errors, compile failures, device load errors, timeouts, or incomplete buffers must result in a non-zero process exit code.

---

## 5. Oracle Independence and Isolation

Test oracles and reference implementations provide independent ground truth and must remain completely isolated from the implementation under test.

- **Isolation Invariant**: Test vectors, expected result corpora, and reference oracles must remain unchanged during implementation repair.
- **Separation of Tasks**: If an oracle is suspected to be erroneous or non-conformant, that investigation constitutes a separate, isolated task, branch, and PR. An agent must never modify both an implementation and its evaluation oracle in the same change.
- **Full Buffer Validation**: Oracle comparisons must evaluate 100% of the complete output buffer (e.g., full 800-byte $ek_{pke}$ and 768-byte $dk_{pke}$ for ML-KEM-512), never partial slices, prefixes, or lengths.
- **Oracle Nomenclature**:
  - Use `independent host reference oracle` when the reference code executes in the same process as the test.
  - Use `parent oracle` strictly when a separate parent process or independent test harness conducts the evaluation.

---

## 6. Ablation-Required Minimality

Kernel corrections must be proven minimal and sufficient through systematic ablation.

- **Ablation Protocol**: When a proposed repair involves multiple candidate modifications:
  1. Designate each candidate change with an explicit identifier (Change A, Change B, Change C, etc.).
  2. Measure and record the failing baseline (Config 0).
  3. Evaluate each change independently and in combination against official vectors.
  4. Record selected, executed, matching, and failing case counts for each configuration.
  5. Identify the earliest divergent intermediate state and the minimal necessary set of changes.
  6. Revert all unproven, speculative, or superfluous modifications.
- **Prohibited Speculation**: Rationale such as "might help," "future-proofing," or "safer" is forbidden. Kernel diffs must be the smallest evidence-supported patch that completely resolves the defect.

---

## 7. Fresh, Hidden, Deterministic, and Regression Terminology

Input and vector classifications must accurately describe vector provenance and availability:

- **Fresh Input**: An input generated strictly after the implementation was frozen, unavailable to the implementation author during development.
- **Hidden Input**: An input whose value remained undisclosed to the implementation and developer until evaluation.
- **Deterministic Regression Input**: An input generated reproducibly from a public, committed algorithm or seed prefix. Once committed, an input is permanently public and deterministic; it must never be described as fresh or hidden in subsequent reports.
- **Official Vector**: An authoritative test vector sourced directly from an identified NIST ACVP, CAVP, or standard specification corpus.

---

## 8. C/C++ and Header Semantic Review

Every modification to `.c`, `.cc`, `.cpp`, `.h`, or `.hpp` files requires exhaustive semantic review:

- **Exhaustive Diff Audit**: Review every modified function, line of code, loop construct, and pragma.
- **Verification Checklist**:
  - Document the rationale for every correctness- or security-relevant line.
  - Audit all pointer arithmetic, array indexing, buffer sizes, data alignment, signedness, integer overflow, modular reductions, and serialization routines.
  - Verify that no test IDs, expected output fragments, or bypass branches exist.
  - Verify that no host fallbacks, catch blocks, or mock paths exist.
- **Compiler Workaround Documentation**: If a change works around a toolchain or compiler defect:
  - Document the exact toolchain version and compiler commit revision.
  - Provide a minimal reproducer and inspect generated IR/disassembly where feasible.
  - Cite the exact upstream issue URL, PR URL, or commit SHA.
  - Clearly distinguish local observations from upstream-confirmed root causes.

---

## 9. Source-to-Artifact Binding

Hardware-compiled artifacts must be deterministically bound to exact source code states:

- **Mandatory Hash Registry**: Every evidence manifest and compilation report must record:
  - Git commit SHA.
  - `COMMITTED_GIT_BLOB` (normalized LF byte stream in Git database).
  - `COMPILED_WORKTREE_INPUT` (exact CRLF/LF bytes on local disk passed to the compiler).
  - Header hashes, generated MLIR IR hashes, object file (`.o`) hashes, XCLBIN hashes, instruction stream (`insts.bin`) hashes, and PDI (`main.pdi`) hashes.
- **CRLF vs LF Distinction**: Acknowledge that Windows worktrees use CRLF line endings while Git objects use normalized LF. Record both hashes when reporting compilation provenance; never claim they must be identical.

---

## 10. Cache Isolation and Reproducibility

Build cache behavior must be transparently reported and verified:

- **Cache Status Reporting**: Reports must state whether artifacts were obtained via a `cache hit` (warm cache) or `fresh compilation` (cold cache).
- **Prohibited Misrepresentation**: A warm cache hit must never be reported as a fresh build.
- **Reproducibility Invariant**: Output buffers and case outcomes must be identical between warm-cache execution and cold-cache fresh compilation. Any discrepancy constitutes an artifact provenance defect and blocks merge.
- **Cross-Branch Cache Isolation**: When comparing branches (e.g., `origin/main` vs PR head), separate cache directories must be used to prevent cross-contamination.

---

## 11. Cross-Gate Regression Blocking

A bounded repair on one deliverable must not cause unintended regressions in other gates:

- **Regression Audit Scope**:
  - For any change that affects kernels, graphs, device runtime, compilation, dispatch, serialization, shared cryptographic code, or hardware-facing behavior, all canonical silicon gates must be executed following the change to ensure zero regressions across unrelated gates.
  - For policy-only, documentation-only, metadata-only, and scanner-test-only changes, the applicable host-safe validation suite, policy scanners, and CI checks must be executed and succeed; physical hardware execution is neither required nor claimed when no hardware-affecting path is changed.
- **Merge Blocker**: If an unrelated gate experiences a status change, count change, or failure regression during hardware-affecting changes, the pull request is blocked from merging until the cause is fully reconciled.
- **Isolation Rule**: Do not attempt to repair an unrelated gate on the current bounded repair branch.

---

## 12. Dynamic Accounting Integrity

All test summaries, console logs, and Markdown reports must derive totals dynamically from machine-readable execution records:

- **Accounting Invariants**:
  $$\begin{aligned}
  \text{cases\_selected} &\ge \text{cases\_executed} \\
  \text{cases\_executed} &= \text{cases\_matching} + \text{cases\_failing} + \text{cases\_skipped} + \text{cases\_xfailed} \\
  \text{cases\_selected} &= \text{cases\_matching} + \text{cases\_failing} + \text{cases\_blocked} \quad (\text{for standard runs})
  \end{aligned}$$
- **Table Integrity**: Detail rows in Markdown tables must sum exactly to the displayed total row. Detail gate IDs, case counts, and positions must match the canonical test runner.
- **Documented DR2d Reporting Failure Lesson**:
  > *Historical Policy Incident*: In an earlier DR2d report, a Markdown table was manually compiled with detail rows summing to 681 (DR0=1 instead of 24, DR9=85 instead of 122, DR10=45 instead of 40) while claiming a total of 736. Although the overall aggregate (664 matching / 72 failing) was correct, the displayed detail table was inconsistent.
  > *Directive*: Manually edited or constructed accounting tables are forbidden. Tables must be generated programmatically or verified dynamically against executed case records.

---

## 13. Exact Identifier Integrity

Identifiers must be verified against authoritative tools and never reconstructed from memory:

- **Authoritative Commands**:
  - `git rev-parse HEAD` (exact commit SHA).
  - `git cat-file -e "<sha>^{commit}"` (commit existence verification).
  - GitHub API / `gh` CLI (PR URLs, workflow run IDs).
- **Prohibitions**: Never guess, abbreviate, or manually expand commit SHAs. Never invent file hashes, timestamps, or artifact sizes.

---

## 14. Exact Citation Integrity

External research citations must be complete, precise, and authoritative:

- **Citation Requirements**: Every external citation must include:
  - Exact URL (full permalink, issue URL, PR URL, or commit SHA).
  - Exact upstream title as published.
  - Author or issuing organization.
  - Applicable version, tag, or commit SHA.
  - Relevant section, equation, or line range.
  - Classification: Normative standard, vendor documentation, upstream source code, peer-reviewed paper, or lead only.
- **Location**: Research records must be maintained in `docs/research/<TASK-ID>-sources.md`, and consequential decisions recorded in `.agent/decisions.md`.

---

## 15. Evidence-Level Separation

Different levels of technical verification must remain strictly separated:

1. Source exists in repository.
2. Source compiles into machine code / MLIR.
3. Artifacts load on target device runtime.
4. Complete output buffers match independent oracle bit-exactly.
5. Implementation is constant-time under a defined architectural model.
6. Implementation resists physical side-channel / fault injection attacks.
7. Implementation is externally certified.

Promoting evidence across levels without independent corroboration is strictly forbidden.

---

## 16. Physical-Claim Vocabulary

While `PHYSICAL-DISPATCH-CORROBORATION` remains OPEN in `.agent/blockers.json`, unqualified physical execution claims are blocked:

- **Prohibited Unqualified Phrases**: Prohibited phrases include "verified physical silicon", "physically verified", "verified on hardware", "confirmed on silicon", "executed on silicon", "passed on silicon", "on-tile silicon", "proven on NPU", and "actual hardware execution confirmed".
- **Allowed Bounded Language**:
  - "Observed through the configured target runtime"
  - "Child self-reported dispatch completed"
  - "Output matched the declared oracle bit-exactly"
  - `SELF_REPORTED_UNVERIFIED` (execution provenance)
  - `PHYSICAL_VERIFICATION_BLOCKED` (physical provenance)

A disclaimer on a nearby line does not authorize an unannotated physical claim on another line.

---

## 17. Static-Scanner Limitations

Static policy scanning is a baseline safety mechanism, not proof of semantic correctness:

- Static scanning checks for forbidden patterns, unannotated claims, hardcoded pass banners, and structural defects.
- Static scanning cannot prove the absence of semantic evasion or algorithmic specialization.
- Zero scanner findings does not prove cryptographic correctness, constant-time behavior, or physical silicon execution.
- Human semantic diff review and rigorous fresh-vector evaluation remain mandatory.

---

## 18. Fail-Closed Behavior

The agent must immediately halt execution, mark the task blocked, and report the condition if:

- An oracle or vector file is modified during an implementation repair task.
- An unrelated gate regresses in behavior or case count.
- Dynamic case accounting or table sums fail to reconcile.
- Required exact commit SHAs or artifact hashes cannot be verified.
- Cache reproducibility fails between cold and warm builds.
- A physical execution claim lacks independent external corroboration.
- Required tests fail or are skipped.
