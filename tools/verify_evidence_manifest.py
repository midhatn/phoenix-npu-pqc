"""Validate a physical-silicon evidence manifest and its artifact hashes."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_integrity import load_json, validate_evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-files", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.manifest.resolve()
    try:
        manifest = load_json(path)
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}")
        return 2
    errors = validate_evidence(manifest, path, check_files=args.check_files)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print(f"VALID: {manifest['dr_id']} bit-exact physical-silicon evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
