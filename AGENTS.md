# Agent Rules: Hardware Ground Truth and Continuation

These rules apply to every agent, subagent, model, terminal session, and
automated refactor in this repository. Optimize for reproducible truth, not
gate counts or passing banners.

## Non-negotiable integrity rules

- Existing documentation, test names, tags, logs, and `PASS` strings are
  claims, not evidence.
- Never hide CPU cryptography behind an NPU API.
- Never catch a hardware failure and return a host, reference, simulated,
  cached, repaired, or precomputed result.
- Missing hardware, compilation failure, device-load failure, timeout,
  incomplete output, or ambiguous backend must fail closed with a non-zero
  exit status.
- Never invent AIE2 intrinsics, headers, registers, memory, compiler flags,
  APIs, standards, citations, DOIs, devices, timings, or benchmark results.
- Placeholder kernels, identity transforms, no-op providers, decorative
  descriptors, fixed outputs, and hardcoded success totals are forbidden.
- Host references must be separate from physical-silicon execution paths.
- Physical tests must validate complete buffers against independent official
  vectors or independently maintained oracles.
- Compilation, dispatch, bit-exact correctness, constant-time review, physical leakage evaluation, and external certification are separate evidence levels.
- NPU residency alone does not prove resistance to timing, power, EM, DMA,
  firmware, fault-injection, or physical attacks.
- External QKD keys or QRNG bytes are inputs to the NPU. Never claim that the
  Phoenix NPU generated them.
- A failed, blocked, host-only, or retracted DR is an acceptable result. A fake
  silicon gate is not.

## Mandatory kernel integrity policy

All agents must strictly obey [.agents/rules/kernel-integrity-policy.md](.agents/rules/kernel-integrity-policy.md), [.agents/rules/zero-speculation-policy.md](.agents/rules/zero-speculation-policy.md), and [.agents/rules/autonomous-execution-constitution.md](.agents/rules/autonomous-execution-constitution.md). Implementations must never specialize to test vectors, embed expected outputs, include fallback paths, or retain unproven modifications.

## Execution labels

Use labels that describe actual execution:

- `[ON-TILE SILICON]`
- `[NPU DATA MOVEMENT]`
- `[HOST RUNTIME]`
- `[HOST FORMATTER]`
- `[HOST REFERENCE]`
- `[SIMULATION]`
- `[COMPILE ONLY]`
- `[BLOCKED]`

Only code compiled into an AIE2 artifact and freshly dispatched through the
real XRT/IRON physical-device path may be labeled `[ON-TILE SILICON]`.

## Mandatory test separation

Keep these evidence classes separate:

1. `host_reference`
2. `contract`
3. `compile_only`
4. `physical_silicon`

A physical suite must reject simulator, emulator, generic, mock, reference,
host, and CPU backends. Zero executed cases, skips, xfails, partial
comparisons, stale evidence, or absent hardware cannot produce a physical
pass.

## Protected verification infrastructure

Changes to these paths require a separate, explicitly reviewed commit:

- `AGENTS.md`
- `.agent/`
- `.agents/rules/`
- `schemas/evidence.schema.json`
- `tools/agent_integrity.py`
- `tools/verify_agent_change.py`
- `tools/verify_evidence_manifest.py`
- `tools/promote_dr_status.py`
- `tests/policy/`

Do not modify policy and cryptographic implementation in the same commit.
Never weaken a policy check to make implementation code pass.

## Required commands

Before completing a normal code change, run:

```text
python tools/verify_agent_change.py
python -m unittest discover -s tests/policy -v
python run_all_pqc_tests.py
```

Physical claims additionally require:

```text
python tools/verify_evidence_manifest.py PATH_TO_MANIFEST --check-files
python tools/promote_dr_status.py PATH_TO_MANIFEST
```

Only `tools/promote_dr_status.py` may set
`BIT_EXACT_PHYSICAL_SILICON_VERIFIED` in `.agent/state.json`.

## Mandatory continuation protocol

At startup:

1. Read this file.
2. Read `.agent/state.json`, `.agent/task_queue.json`,
   `.agent/current_task.md`, `.agent/blockers.json`, and `.agent/handoff.md`.
3. Inspect `git status`, `git log -1`, and relevant evidence.
4. Confirm that the recorded state commit is `HEAD` or an ancestor of `HEAD`.
   If it is an ancestor, inspect every intervening commit before updating the
   checkpoint. If it is unrelated to `HEAD`, stop and reconcile the state.
5. Resume the first ready unfinished task. Do not repeat completed work.

After every meaningful implementation or diagnostic result:

1. Update `.agent/state.json`.
2. Append the command, exit code, timestamp, and result to
   `.agent/session_log.jsonl`.
3. Update `.agent/current_task.md`.
4. Record blockers in `.agent/blockers.json`.
5. Put exactly one precise next action in `.agent/handoff.md`.

Before context exhaustion or termination:

1. Stop beginning new work.
2. Finish or revert the current atomic edit.
3. Run the relevant deterministic checks.
4. Record changed files, commands, results, evidence, and unresolved risks.
5. Leave a clean, resumable working state whenever possible.
6. Set exactly one `next_action`.

Never mark a task complete from prose reasoning. The corresponding
deterministic acceptance command must succeed.

## Stop conditions

Stop and mark the affected DR failed, blocked, or retracted if:

- Actual execution location cannot be proven.
- The specification cannot be verified.
- A required documented hardware operation does not exist.
- The independent oracle disagrees with the complete device output.
- CPU repair or fallback is reachable.
- Evidence is stale, contradictory, incomplete, or from another commit.
- Security language exceeds demonstrated analysis.

Record the blocker and continue with independent tasks. Never bypass a stop
condition to make the roadmap appear complete.

# External Research Escalation and Citation Provenance

When a technical problem cannot be resolved from the repository, existing
tests, installed dependency source, or official local documentation, the agent
must research the problem before declaring it blocked.

## Required escalation sequence

1. Reproduce and minimize the problem locally.
2. Search the repository history, issues, tests, and dependency source.
3. Consult the governing standard or protocol specification.
4. Consult official vendor documentation.
5. Search upstream source repositories, issues, discussions, pull requests,
   release notes, and reference implementations.
6. Search peer-reviewed papers, conference papers, technical reports, and
   preprints.
7. Search Stack Overflow and other technical forums.
8. Search Reddit or informal community discussions for additional leads.
9. Cross-check proposed solutions against primary sources and local tests.

Do not stop after the first plausible answer.

## Source authority

Use this priority order:

1. Normative standards and official specifications
2. Official AMD, NIST, IETF, ETSI, 3GPP, TCG, OpenSSL, or project
   documentation
3. Upstream source code and version-pinned reference implementations
4. Peer-reviewed research
5. Maintainer-authored GitHub issues, discussions, and pull requests
6. Stack Overflow answers with reproducible technical evidence
7. Reddit and other community discussions

Reddit, forum posts, AI-generated answers, and unverified comments are leads,
not ground truth. Their claims must be verified against source code, official
documentation, standards, or reproducible experiments.

## Required citation record

For every external source that influences code, architecture, tests, or a
technical decision, record:

- source title
- author or organization
- source type
- full URL
- publication or update date, if available
- access date in timezone-aware ISO-8601 format
- applicable version, release, tag, or Git commit
- relevant section, page, issue, answer, or line range
- exact technical claim taken from the source
- how the claim was independently verified
- which repository files or decisions it affected
- confidence level: PRIMARY, CORROBORATED, LEAD_ONLY, or REJECTED

Do not cite only a search-results page or search snippet. Open and inspect the
actual source.

## Documentation location

Create one research ledger per affected task:

docs/research/<TASK-ID>-sources.md

For example:

docs/research/FIX-DR2D-FUNCTIONAL-MISMATCH-sources.md

Also summarize the resulting engineering decision in:

.agent/decisions.md

If research produces a blocker rather than a solution, reference the research
ledger from:

.agent/blockers.json

## GitHub source requirements

For GitHub evidence, record:

- repository owner and name
- file, issue, discussion, pull request, or commit URL
- exact tag or commit SHA
- relevant lines or comment permalink
- license
- whether code was copied, adapted, or only consulted

Do not cite a moving branch such as main without also recording the inspected
commit SHA.

## Research-paper requirements

For papers, record:

- full title
- authors
- venue
- year
- DOI, publisher URL, or arXiv identifier
- exact page, section, equation, algorithm, or table used

Never invent a DOI, title, author, or publication status.

## Standards requirements

For standards, record:

- issuing organization
- complete standard identifier
- revision or publication date
- exact section, algorithm, equation, or table
- official URL

Distinguish normative requirements from informative guidance.

## Code provenance and licensing

If external code is copied or adapted:

- verify that its license permits the intended use
- retain required copyright and license notices
- update THIRD_PARTY_PROVENANCE.md
- identify copied versus independently rewritten portions
- pin the upstream commit
- add conformance tests against the authoritative source

Do not copy code from Stack Overflow, Reddit, a paper, or GitHub without
checking its license and documenting provenance.

## Privacy boundary

Never upload private repository code, secrets, keys, unpublished vectors,
device identifiers, logs containing personal paths, or confidential data to
an external service.

Search using a minimized and sanitized description of the problem.

## Research failure behavior

If no reliable solution is found:

1. Document all queries and sources inspected.
2. Record why each candidate solution was accepted, rejected, or insufficient.
3. Create a precise blocker.
4. State what evidence, hardware access, documentation, or upstream response
   is required.
5. Continue with the next independent READY task.

Do not fabricate a solution to avoid reporting a blocker.

## Implementation gate

External research does not itself prove correctness.

Before accepting a researched solution:

- implement it in a bounded change
- add regression tests
- compare against authoritative vectors where applicable
- run host-safe validation
- run physical validation when required and available
- preserve the correct execution-boundary and evidence classification
