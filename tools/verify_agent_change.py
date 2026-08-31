"""Reject integrity violations introduced by an agent-authored change across all languages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_integrity import (
    REPO_ROOT,
    git_changed_files,
    repository_files,
    scan_paths,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Git base revision for committed changes")
    parser.add_argument("--head", help="Optional Git head revision")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Strictly scan all covered repository files (.py, .c, .cc, .cpp, .h, .hpp, .mlir, .ps1, .sh, .cmake, .yml, .yaml, .json, .md)",
    )
    parser.add_argument("--report", type=Path, help="Write structured JSON findings")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = (
        repository_files()
        if args.all
        else git_changed_files(args.base, args.head)
    )
    findings = scan_paths(paths)
    for finding in findings:
        print(
            f"{finding.severity.upper():8} {finding.rule} "
            f"{finding.path}:{finding.line}: {finding.message}"
        )
    if args.report:
        report = args.report if args.report.is_absolute() else REPO_ROOT / args.report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "scope": "repository" if args.all else "changed",
                    "files_scanned": [path.as_posix() for path in paths],
                    "findings": [item.to_dict() for item in findings],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    blocking = [
        finding
        for finding in findings
        if finding.severity in {"critical", "error"}
    ]
    print(
        f"Scanned {len(paths)} file(s) across all languages: "
        f"{len(blocking)} blocking, {len(findings) - len(blocking)} warning."
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
