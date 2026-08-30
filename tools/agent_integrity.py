#!/usr/bin/env python3
"""Shared integrity checks for agent-authored repository changes."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_SUFFIX = "_silicon.py"
HOST_CRYPTO_MODULES = {
    "Crypto",
    "cryptography",
    "hashlib",
    "hmac",
    "nacl",
}
FALLBACK_TOKENS = ("cpu", "fallback", "host", "reference", "simulate", "mock")
EXCLUDED_POLICY_PATHS = {
    Path("tools/agent_integrity.py"),
}
HARDCODED_PASS_RE = re.compile(
    r"\b\d+\s*/\s*\d+\s+(?:TESTS?\s+)?PASS\b", re.IGNORECASE
)
SELF_DECLARED_BACKEND_RE = re.compile(
    r"Backend\s*:\s*.*(?:silicon|AIE2|NPU)", re.IGNORECASE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def git_changed_python_files(
    base: str | None = None, head: str | None = None
) -> list[Path]:
    """Return changed tracked/untracked Python paths relative to the repository."""
    if base:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMR", base]
        if head:
            command.append(head)
    else:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"]
    result = subprocess.run(
        command, cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    paths = {Path(line) for line in result.stdout.splitlines() if line.endswith(".py")}
    if not base:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths.update(
            Path(line)
            for line in untracked.stdout.splitlines()
            if line.endswith(".py")
        )
    return sorted(path for path in paths if (REPO_ROOT / path).is_file())


def repository_python_files() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = {*tracked.stdout.splitlines(), *untracked.stdout.splitlines()}
    return sorted(
        Path(line) for line in lines if line and (REPO_ROOT / line).is_file()
    )


class PythonPolicyVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self.in_except = 0

    def add(self, node: ast.AST, rule: str, severity: str, message: str) -> None:
        self.findings.append(
            Finding(
                path=self.path.as_posix(),
                line=getattr(node, "lineno", 1),
                rule=rule,
                severity=severity,
                message=message,
            )
        )

    def visit_Assert(self, node: ast.Assert) -> None:
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            self.add(
                node,
                "PY001",
                "critical",
                "Unconditional `assert True` cannot validate implementation behavior.",
            )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self.path.name.endswith(PHYSICAL_SUFFIX):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in HOST_CRYPTO_MODULES:
                    self.add(
                        node,
                        "HW001",
                        "critical",
                        f"Physical test imports host cryptography module `{root}`.",
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.path.name.endswith(PHYSICAL_SUFFIX) and node.module:
            root = node.module.split(".", 1)[0]
            if root in HOST_CRYPTO_MODULES:
                self.add(
                    node,
                    "HW001",
                    "critical",
                    f"Physical test imports host cryptography module `{root}`.",
                )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.in_except += 1
        for child in node.body:
            self.visit(child)
        self.in_except -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if self.in_except and self.path.name.endswith(PHYSICAL_SUFFIX):
            name = call_name(node.func).lower()
            if any(token in name for token in FALLBACK_TOKENS):
                self.add(
                    node,
                    "HW002",
                    "critical",
                    f"Fallback-like call `{name}` is reachable from an exception handler.",
                )
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self.path.name.endswith(PHYSICAL_SUFFIX):
            operands = [node.left, *node.comparators]
            for operand in operands:
                if isinstance(operand, ast.Subscript):
                    slice_node = operand.slice
                    if isinstance(slice_node, ast.Slice) or isinstance(
                        slice_node, ast.Constant
                    ):
                        self.add(
                            node,
                            "TEST001",
                            "warning",
                            "Physical test comparison may cover only a slice or one element.",
                        )
                        break
        self.generic_visit(node)


def call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{call_name(node.value)}.{node.attr}"
    return "<dynamic>"


def scan_python_file(relative_path: Path) -> list[Finding]:
    if (
        relative_path in EXCLUDED_POLICY_PATHS
        or relative_path.parts[:2] == ("tests", "policy")
    ):
        return []
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    findings: list[Finding] = []
    try:
        tree = ast.parse(source, filename=str(relative_path))
    except SyntaxError as exc:
        return [
            Finding(
                path=relative_path.as_posix(),
                line=exc.lineno or 1,
                rule="PY000",
                severity="critical",
                message=f"Python syntax error: {exc.msg}",
            )
        ]
    visitor = PythonPolicyVisitor(relative_path)
    visitor.visit(tree)
    findings.extend(visitor.findings)
    for line_number, line in enumerate(source.splitlines(), start=1):
        if HARDCODED_PASS_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "TEST002",
                    "critical",
                    "Hardcoded passing count is forbidden; aggregate structured results.",
                )
            )
        if (
            relative_path.name.endswith(PHYSICAL_SUFFIX)
            and SELF_DECLARED_BACKEND_RE.search(line)
        ):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "HW003",
                    "warning",
                    "Printed backend label is not evidence of physical dispatch.",
                )
            )
    return findings


def scan_paths(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        findings.extend(scan_python_file(path))
    return sorted(findings, key=lambda item: (item.path, item.line, item.rule))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object")
    return value


def validate_evidence(
    manifest: dict[str, object],
    manifest_path: Path,
    check_files: bool = False,
) -> list[str]:
    """Validate the strict physical-silicon evidence invariants."""
    errors: list[str] = []

    def require_object(parent: dict[str, object], key: str) -> dict[str, object]:
        value = parent.get(key)
        if not isinstance(value, dict):
            errors.append(f"`{key}` must be an object")
            return {}
        return value

    if manifest.get("schema_version") != 1:
        errors.append("`schema_version` must equal 1")
    dr_id = manifest.get("dr_id")
    if not isinstance(dr_id, str) or not re.fullmatch(r"DR(?:[0-9]+|2[a-d])", dr_id):
        errors.append("`dr_id` must be a DR identifier")
    if manifest.get("evidence_class") != "BIT_EXACT_PHYSICAL_SILICON":
        errors.append("`evidence_class` must equal BIT_EXACT_PHYSICAL_SILICON")

    repository = require_object(manifest, "repository")
    commit = repository.get("commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        errors.append("`repository.commit` must be a 40-character lowercase Git hash")
    if repository.get("clean") is not True:
        errors.append("`repository.clean` must be true")

    for section, fields in {
        "hardware": ("device_name", "device_id", "driver", "firmware"),
        "toolchain": ("python", "mlir_aie", "llvm_aie", "xrt"),
    }.items():
        value = require_object(manifest, section)
        for field in fields:
            if not isinstance(value.get(field), str) or not value.get(field):
                errors.append(f"`{section}.{field}` must be a non-empty string")
    hardware = require_object(manifest, "hardware")
    if hardware.get("physical_device") is not True:
        errors.append("`hardware.physical_device` must be true")

    execution = require_object(manifest, "execution")
    command = execution.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        errors.append("`execution.command` must be a non-empty string array")
    if execution.get("exit_code") != 0:
        errors.append("`execution.exit_code` must equal 0")
    dispatches = execution.get("physical_dispatches")
    if not isinstance(dispatches, int) or isinstance(dispatches, bool) or dispatches < 1:
        errors.append("`execution.physical_dispatches` must be a positive integer")
    counts = {}
    for field in (
        "cases_selected",
        "cases_executed",
        "cases_passed",
        "cases_failed",
        "cases_skipped",
        "cases_xfailed",
    ):
        value = execution.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"`execution.{field}` must be a non-negative integer")
        else:
            counts[field] = value
    if counts:
        if counts.get("cases_selected", 0) < 1:
            errors.append("at least one case must be selected")
        if not (
            counts.get("cases_selected")
            == counts.get("cases_executed")
            == counts.get("cases_passed")
        ):
            errors.append("selected, executed, and passed case counts must match")
        for field in ("cases_failed", "cases_skipped", "cases_xfailed"):
            if counts.get(field) != 0:
                errors.append(f"`execution.{field}` must equal 0")
    parsed_times: dict[str, datetime] = {}
    for field in ("started_at", "ended_at"):
        if not isinstance(execution.get(field), str) or not execution.get(field):
            errors.append(f"`execution.{field}` must be a non-empty timestamp")
            continue
        try:
            parsed_times[field] = datetime.fromisoformat(
                str(execution[field]).replace("Z", "+00:00")
            )
        except ValueError:
            errors.append(f"`execution.{field}` must be an ISO-8601 timestamp")
    if (
        "started_at" in parsed_times
        and "ended_at" in parsed_times
        and parsed_times["ended_at"] < parsed_times["started_at"]
    ):
        errors.append("`execution.ended_at` must not precede `started_at`")

    comparisons = manifest.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        errors.append("`comparisons` must contain at least one full-buffer comparison")
    else:
        case_ids: list[str] = []
        for index, comparison in enumerate(comparisons):
            if not isinstance(comparison, dict):
                errors.append(f"`comparisons[{index}]` must be an object")
                continue
            if not comparison.get("case_id"):
                errors.append(f"`comparisons[{index}].case_id` is required")
            else:
                case_ids.append(str(comparison["case_id"]))
            if comparison.get("full_buffer") is not True:
                errors.append(f"`comparisons[{index}].full_buffer` must be true")
            expected = comparison.get("expected_sha256")
            actual = comparison.get("actual_sha256")
            if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                errors.append(f"`comparisons[{index}].expected_sha256` is invalid")
            if not isinstance(actual, str) or not SHA256_RE.fullmatch(actual):
                errors.append(f"`comparisons[{index}].actual_sha256` is invalid")
            if expected != actual:
                errors.append(f"`comparisons[{index}]` expected and actual hashes differ")
        if len(case_ids) != len(set(case_ids)):
            errors.append("comparison case identifiers must be unique")
        if "cases_passed" in counts and len(comparisons) != counts["cases_passed"]:
            errors.append("one full-buffer comparison is required per passed case")

    negative = require_object(manifest, "negative_tests")
    for field in ("device_absence_nonzero", "host_reference_disabled_pass"):
        if negative.get(field) is not True:
            errors.append(f"`negative_tests.{field}` must be true")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("`artifacts` must contain at least one hashed file")
    else:
        roles: set[str] = set()
        allowed_roles = {
            "device_info",
            "compiler_log",
            "runtime_log",
            "case_results",
            "aie_artifact",
            "graph_ir",
            "source_snapshot",
            "other",
        }
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                errors.append(f"`artifacts[{index}]` must be an object")
                continue
            relative = artifact.get("path")
            expected_hash = artifact.get("sha256")
            role = artifact.get("role")
            if role not in allowed_roles:
                errors.append(f"`artifacts[{index}].role` is invalid")
            else:
                roles.add(str(role))
            if not isinstance(relative, str) or not relative:
                errors.append(f"`artifacts[{index}].path` is required")
                continue
            if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
                errors.append(f"`artifacts[{index}].sha256` is invalid")
                continue
            if check_files:
                artifact_path = (manifest_path.parent / relative).resolve()
                try:
                    artifact_path.relative_to(manifest_path.parent.resolve())
                except ValueError:
                    errors.append(f"`artifacts[{index}].path` escapes the evidence directory")
                    continue
                if not artifact_path.is_file():
                    errors.append(f"artifact not found: {relative}")
                elif sha256_file(artifact_path) != expected_hash:
                    errors.append(f"artifact hash mismatch: {relative}")
        required_roles = {
            "device_info",
            "compiler_log",
            "runtime_log",
            "case_results",
            "aie_artifact",
        }
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            errors.append(
                "required evidence artifact roles missing: " + ", ".join(missing_roles)
            )
    return errors
