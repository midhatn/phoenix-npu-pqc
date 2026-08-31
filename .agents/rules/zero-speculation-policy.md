---
trigger: always_on
---

# Agent Directive: Hardware Ground Truth and Zero-Fabrication Engineering

This directive is mandatory for every agent, subagent, model, terminal session, code-generation tool, and automated refactor operating in this repository. If another instruction conflicts with this directive, choose the behavior that preserves evidence, security, and truthful labeling.

## Ground truth

- Existing code, documentation, test names, tags, releases, badges, and status labels are claims, not proof.
- Never optimize for passing banners, gate counts, roadmap completion, or appearance.
- Never claim more than current, reproducible evidence demonstrates.
- A failed or blocked gate is an acceptable engineering result. A fake passing gate is not.

## Execution boundary

Every relevant module and function must be labeled according to actual execution:

- `[ON-TILE SILICON]`
- `[NPU DATA MOVEMENT]`
- `[HOST RUNTIME]`
- `[HOST FORMATTER]`
- `[HOST REFERENCE]`
- `[SIMULATION]`
- `[COMPILE ONLY]`
- `[BLOCKED]`

Only code compiled into an AIE2 tile artifact and freshly dispatched through the real XRT/IRON physical-device path may be labeled `[ON-TILE SILICON]`.

Host orchestration is allowed. Host cryptographic fallback inside a physical-silicon gate is forbidden.

## Fail-closed hardware behavior

- Missing physical hardware, driver failure, firmware mismatch, buffer-allocation failure, compile failure, device-load failure, timeout, runtime exception, incomplete output, or backend ambiguity must produce a non-zero exit code.
- Never catch a hardware error and return a CPU, Python, OpenSSL, reference, simulator, mock, cached, or precomputed result.
- Never skip a physical test because hardware is unavailable and report the suite as passed.
- Physical tests must reject simulator, emulator, reference, generic, host, CPU, and mock backends.
- A physical suite with zero executed cases is a failure.

## No fake implementation

Forbidden:

- Placeholder kernels, identity transforms, byte-copy kernels, fixed outputs, no-op functions, null dispatch tables, decorative structs, or arbitrary magic constants represented as completed features.
- Invented AIE2 intrinsics, headers, registers, tile features, compiler flags, or runtime APIs.
- Restoring reverted milestone code without reimplementation and new evidence.
- Comments, docstrings, or design documents that describe behavior not present in the AST, generated IR, machine code, and runtime path.

If the hardware cannot implement a requirement, document the blocker and, if useful, create a clearly separate `[HOST REFERENCE]`. Never count it as an NPU gate.

## Cryptographic correctness

- Verify algorithms, constants, byte ordering, encodings, bounds, and parameter sets against official primary specifications.
- Use complete official KAT/ACVP/CAVP vectors where available.
- Validate complete output buffers. Prefix, one-byte, non-null, length-only, checksum-only, or `assert True` tests are forbidden.
- Expected values must come from an independent oracle or authoritative vector source, not from the implementation under test.
- Never modify expected outputs after observing device output.
- Never reduce test coverage or weaken an assertion to obtain a pass.
- Run adversarial, malformed, boundary, stale-buffer, canary, and device-absence tests.

## Proof levels must remain separate

These statements are not equivalent:

1. Source exists.
2. Source compiles.
3. AIE2 artifacts are generated.
4. The runtime dispatches to a physical device.
5. The device writes an output.
6. The complete output is bit-exact.
7. The implementation is constant-time under a defined model.
8. The implementation resists timing, cache, power, EM, fault, DMA, and physical attacks.
9. The implementation is externally certified.

Never promote evidence from one level to another.

## Side-channel rigor

- NPU-only execution does not prove side-channel resistance.
- Identify public and secret inputs.
- Prohibit secret-dependent branches, loop bounds, memory addresses, early exits, and table indexes where required.
- Inspect compiler output to ensure constant-time source patterns survive compilation.
- Use constant-time comparisons and selections.
- Record timing-test methodology and limitations.
- TVLA claims require valid fixed-versus-random trace acquisition and statistical analysis. Host timing or process counters are not a substitute for physical power/EM traces.
- Masking claims require a documented masking order, validated gadgets, non-reuse arguments, and a suitable randomness source.
- Formal proofs must state the exact modeled property and assumptions.
- Never use “side-channel secure,” “constant-time,” “DPA resistant,” or “fault resistant” without bounded supporting evidence.

## QKD and entropy truthfulness

- External optical keys or quantum entropy transported into the NPU are external inputs. Do not claim that the Phoenix NPU generated them.
- Buffer ingress, CRC32, queue management, token comparison, copying, and XOR are not cryptographic authentication or key derivation.
- A combiner must match the selected authoritative construction exactly.
- Entropy health tests do not create entropy and do not prove that a source is quantum.
- Do not store or print production keys, tokens, seeds, or sensitive captures.

## Tests and runners

- Separate `host_reference`, `contract`, `compile_only`, and `physical_silicon` suites.
- Derive totals dynamically from executed structured results.
- Hardcoded pass counts, pass percentages, device names, timings, and backend labels are forbidden.
- Treat skipped, xfailed, unavailable, unexecuted, and partial-comparison cases as not physically verified.
- A zero exit code is necessary but insufficient. Inspect structured case results and forbidden backend markers.
- Preserve stdout, stderr, commands, artifact hashes, environment, and per-case results for physical evidence.

## Documentation and provenance

- Cite only verified publications and official sources.
- Never fabricate DOIs, badges, release records, benchmark values, institutional affiliations, or certification claims.
- Use “implements” only for real code, “compile verified” only for current compiler evidence, and “physical-silicon verified” only for a fresh physical run.
- Do not use “certified,” “FIPS compliant,” “NIST approved,” “first,” or equivalent language without authoritative evidence and exact scope.
- Correct or retract inaccurate documentation as soon as it is found.

## Required per-change check

Before declaring a change complete:

1. Inspect the diff for fake, dead, host-fallback, or decorative code.
2. Trace the runtime call path.
3. Verify the specification and provenance.
4. Compile the relevant AIE2 artifacts.
5. Run the correct evidence-class tests.
6. Run negative device-absence/failure tests.
7. Confirm full-buffer comparison.
8. Inspect generated artifacts where the claim depends on vectorization or constant-time behavior.
9. Update DR status and limitations.
10. Report failures and blockers without hiding them.

## Stop conditions

Stop the affected gate and mark it failed, blocked, or retracted if:

- Actual execution location cannot be proven.
- An official specification cannot be verified.
- A required hardware operation or documented API does not exist.
- The independent oracle disagrees with device output.
- The test depends on CPU repair or fallback.
- Evidence is missing, stale, contradictory, or generated from another commit.
- Security language exceeds demonstrated analysis.

Continue work on independent gates after documenting the blocker. Never bypass a stop condition just to finish the roadmap.

## Final integrity rule

It is acceptable for some DRs to remain host integrations, references, blocked research, or future work. It is never acceptable to convert those categories into fake silicon gates.

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
