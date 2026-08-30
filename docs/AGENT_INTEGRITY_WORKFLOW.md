# Agent Integrity and Continuation Workflow

This repository uses deterministic policy and evidence checks to prevent an
agent-generated implementation from promoting itself through prose, filenames,
or hardcoded output.

## Components

- `AGENTS.md` defines mandatory ground-truth and continuation rules.
- `.agent/state.json` stores DR status independently of an IDE conversation.
- `.agent/task_queue.json` stores bounded resumable tasks.
- `.agent/blockers.json` records reproducible blockers.
- `.agent/session_log.jsonl` is an append-only command/result journal.
- `.agent/current_task.md` and `.agent/handoff.md` provide human-readable
  recovery context.
- `tools/verify_agent_change.py` scans new or changed Python code for critical
  integrity violations.
- `tools/verify_evidence_manifest.py` validates physical-silicon evidence.
- `tools/promote_dr_status.py` is the only supported command that may promote a
  DR to `BIT_EXACT_PHYSICAL_SILICON_VERIFIED`.
- `schemas/evidence.schema.json` documents the evidence format.

## Ordinary change validation

Run from the repository root:

```powershell
python tools/verify_agent_change.py
python -m unittest discover -s tests/policy -t . -v
python run_all_pqc_tests.py
```

The default policy scan checks uncommitted Python files and differences from
`HEAD`. For a committed range:

```powershell
python tools/verify_agent_change.py --base <base-commit> --head <head-commit>
```

To expose all known legacy violations:

```powershell
python tools/verify_agent_change.py --all
```

Strict repository scanning may fail while historical findings remain. Do not
silence those findings. Convert each one into a bounded cleanup task.

## Physical evidence directory

Keep generated physical evidence outside tracked source by default, for
example:

```text
release-evidence/
└── DR9/
    └── 2026-08-31T030000+0300/
        ├── manifest.json
        ├── compile.log
        ├── runtime.log
        ├── graph.mlir
        ├── worker.elf
        └── case-results.jsonl
```

Every artifact listed in `manifest.json` must use a path relative to the
manifest directory and include its SHA-256 digest. Paths that escape the
evidence directory are rejected.

## Evidence validation and promotion

Validate the manifest and every listed artifact:

```powershell
python tools/verify_evidence_manifest.py `
  release-evidence/DR9/<run>/manifest.json `
  --check-files
```

Promotion additionally requires:

- Manifest repository commit equals current `HEAD`.
- Manifest says the evidence run used a clean repository.
- Current working tree contains no changes except a possible pending
  `.agent/state.json` update.
- At least one case was selected, executed, and passed.
- Selected, executed, and passed counts are identical.
- Failed, skipped, and xfailed counts are zero.
- Every expected and actual full-buffer SHA-256 pair matches.
- Device-absence testing returned non-zero.
- Physical execution still passed with the host reference disabled.
- Every recorded evidence artifact exists and matches its hash.

Then run:

```powershell
python tools/promote_dr_status.py `
  release-evidence/DR9/<run>/manifest.json
```

The promotion updates only functional status. It deliberately does not promote
side-channel or certification status.

## Recovery after interruption

A replacement agent must:

1. Read `AGENTS.md` and every file under `.agent/`.
2. Confirm that `.agent/state.json` records `HEAD` or an ancestor of `HEAD`,
   then inspect any intervening commits and the working tree.
3. Read the most recent session-log entries.
4. Resume exactly the `next_action` in `.agent/handoff.md`.
5. Update state after each meaningful command or result.

If state and Git disagree, stop and reconcile them. Never infer successful
completion from an abandoned working tree.

## Policy-change discipline

Do not combine cryptographic implementation changes with edits to policy,
evidence validation, or promotion code. Policy changes need a separate commit
and independent review because otherwise an implementation agent could weaken
the checks that judge its own work.
