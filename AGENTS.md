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
- Compilation, dispatch, bit-exact correctness, constant-time review,
  physical leakage evaluation, and external certification are separate
  evidence levels.
- NPU residency alone does not prove resistance to timing, power, EM, DMA,
  firmware, fault-injection, or physical attacks.
- External QKD keys or QRNG bytes are inputs to the NPU. Never claim that the
  Phoenix NPU generated them.
- A failed, blocked, host-only, or retracted DR is an acceptable result. A fake
  silicon gate is not.

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
