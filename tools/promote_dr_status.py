"""Promote a DR only after strict physical-silicon evidence validation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

from agent_integrity import REPO_ROOT, load_json, validate_evidence


STATE_PATH = REPO_ROOT / ".agent" / "state.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


def git_output(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def atomic_write_json(path: Path, value: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    evidence_root = (REPO_ROOT / "release-evidence").resolve()
    try:
        manifest_path.relative_to(evidence_root)
    except ValueError:
        print(f"REFUSED: manifest must be under {evidence_root}")
        return 1
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    errors = validate_evidence(manifest, manifest_path, check_files=True)
    if errors:
        for error in errors:
            print(f"REFUSED: {error}")
        return 1

    evidence_commit = manifest["repository"]["commit"]
    head = git_output("rev-parse", "HEAD")
    if evidence_commit != head:
        print(f"REFUSED: evidence commit {evidence_commit} does not match HEAD {head}")
        return 1

    status_lines = [
        line
        for line in git_output("status", "--porcelain").splitlines()
        if not line.endswith(" .agent/state.json")
    ]
    if status_lines:
        print("REFUSED: working tree contains changes beyond .agent/state.json")
        return 1

    state = load_json(STATE_PATH)
    dr_id = manifest["dr_id"]
    drs = state.get("drs")
    if not isinstance(drs, dict) or dr_id not in drs:
        print(f"REFUSED: {dr_id} is not registered in .agent/state.json")
        return 1
    dr_state = drs[dr_id]
    if not isinstance(dr_state, dict):
        print(f"REFUSED: invalid state object for {dr_id}")
        return 1
    dr_state["functional_status"] = "BIT_EXACT_PHYSICAL_SILICON_VERIFIED"
    dr_state["evidence_class"] = "BIT_EXACT_PHYSICAL_SILICON"
    dr_state["last_evidence_manifest"] = str(manifest_path)
    dr_state["last_verified_commit"] = evidence_commit
    dr_state["promoted_at"] = datetime.now(timezone.utc).isoformat()
    dr_state["next_action"] = "Perform or update the separately scoped security evaluation."
    state["last_verified_commit"] = evidence_commit
    state["repository_commit"] = head
    atomic_write_json(STATE_PATH, state)
    print(f"PROMOTED: {dr_id} at {evidence_commit}")
    print("SECURITY STATUS NOT PROMOTED: functional evidence is not side-channel proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
