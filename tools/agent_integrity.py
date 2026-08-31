"""Shared integrity and policy checks for repository changes across all languages."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

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

SUPPORTED_EXTENSIONS = {
    ".py",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".mlir",
    ".ps1",
    ".sh",
    ".cmake",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".editorconfig",
}
SPECIAL_FILENAMES = {
    "CMakeLists.txt",
    "install",
}

# Regex patterns for integrity rules
HARDCODED_PASS_RE = re.compile(
    r"\b\d+\s*/\s*\d+\s+(?:TESTS?\s+)?PASS(?:ED|ING)?\b", re.IGNORECASE
)
SELF_DECLARED_BACKEND_RE = re.compile(
    r"Backend\s*:\s*.*(?:silicon|AIE2|NPU)", re.IGNORECASE
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# C/C++ patterns
CPP_TRIVIAL_ASSERT_RE = re.compile(
    r"\b(?:assert|static_assert)\s*\(\s*(?:true|1)\s*[,)]"
)
CPP_CATCH_FALLBACK_RE = re.compile(
    r"catch\s*\([^)]*\)\s*\{[^}]*(?:cpu|host|fallback|simulate|mock|reference)",
    re.IGNORECASE | re.DOTALL,
)
CPP_PREPROCESSOR_FALLBACK_RE = re.compile(
    r"#(?:if|ifdef)\s+.*(?:CPU_FALLBACK|HOST_FALLBACK|USE_HOST|USE_SIMULATOR)\b"
)
CPP_UNSAFE_MEMCPY_RE = re.compile(r"\bmemcpy\s*\(\s*[^,]+,\s*[^,]+,\s*0\s*\)")

# Script patterns
SCRIPT_IGNORED_EXIT_RE = re.compile(
    r"(?:\$LASTEXITCODE\s*=\s*0|\|\|\s*(?:true|exit\s+0))\b"
)
SCRIPT_SILENTLY_CONTINUE_RE = re.compile(
    r"(?i)(?:\$ErrorActionPreference\s*=\s*['\"]?SilentlyContinue['\"]?|-ErrorAction\s+['\"]?SilentlyContinue['\"]?)"
)
SCRIPT_GENERIC_PYTHON_FALLBACK_RE = re.compile(
    r"if\s*\([^)]*(?:ironenv|iron_python)[^)]*\)\s*\{[^}]*python",
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_DESTRUCTIVE_CMD_RE = re.compile(
    r"(?:rm\s+-rf\s+/(?:\s|$|\*)|Remove-Item\s+-(?:Force\s+)?-Recurse\s+['\"]?[A-Za-z]:\\[*]?['\"])"
)

# Secret and privacy patterns
SECRET_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----")
SECRET_API_KEY_RE = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}\b|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\bsk_live_[0-9a-zA-Z]{24,}\b"
)
SECRET_PERSONAL_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:\\users\\(?!default\b|public\b|runneradmin\b)[a-z0-9_.-]+|/home/(?!runner\b|ubuntu\b|test\b|dev\b)[a-z0-9_.-]+)"
)

# Documentation claim patterns
DOC_STRONG_CLAIM_RE = re.compile(
    r"(?i)\[VERIFIED PHYSICAL SILICON\]|"
    r"\bphysically verified\b|"
    r"\bexecuted on silicon\b|"
    r"\bhardware accelerated\b|"
    r"\bstandards compliant\b|"
    r"\bconstant[- ]time\b|"
    r"\bside[- ]channel resistant\b|"
    r"\bproduction ready\b|"
    r"\b\d+\s*/\s*\d+\s+(?:TESTS?\s+)?PASS(?:ED|ING)?\b"
)
CLAIM_PROVENANCE_RE = re.compile(r"\[CLAIM-PROVENANCE:\s*([^\]]+)\]", re.IGNORECASE)


@dataclass
class ClaimProvenance:
    raw: str
    status: str
    evidence: str | None = None
    commit: str | None = None
    classification: str | None = None
    source: str | None = None
    line: int = 1


def parse_claim_provenance(line_number: int, text: str) -> ClaimProvenance | None:
    match = CLAIM_PROVENANCE_RE.search(text)
    if not match:
        return None
    body = match.group(1)
    fields: dict[str, str] = {}
    for part in body.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k.strip().lower()] = v.strip()

    status = fields.get("status", "").upper()
    return ClaimProvenance(
        raw=match.group(0),
        status=status,
        evidence=fields.get("evidence"),
        commit=fields.get("commit"),
        classification=fields.get("classification", "").upper()
        if "classification" in fields
        else None,
        source=fields.get("source"),
        line=line_number,
    )


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS or path.name in SPECIAL_FILENAMES


def is_policy_exempt(relative_path: Path) -> bool:
    return relative_path in EXCLUDED_POLICY_PATHS


def git_changed_files(base: str | None = None, head: str | None = None) -> list[Path]:
    """Return changed tracked and untracked supported paths relative to repository."""
    if base:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMR", base]
        if head:
            command.append(head)
    else:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"]
    result = subprocess.run(
        command, cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    paths = {
        Path(line)
        for line in result.stdout.splitlines()
        if is_supported_file(Path(line))
    }
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
            if is_supported_file(Path(line))
        )
    return sorted(path for path in paths if (REPO_ROOT / path).is_file())


def repository_files() -> list[Path]:
    """Return all tracked and untracked supported repository files."""
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = {*tracked.stdout.splitlines(), *untracked.stdout.splitlines()}
    return sorted(
        Path(line)
        for line in lines
        if line and is_supported_file(Path(line)) and (REPO_ROOT / line).is_file()
    )


# Backward compatibility aliases
git_changed_python_files = git_changed_files
repository_python_files = repository_files


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
        if isinstance(node.test, ast.Constant) and (
            node.test.value is True or node.test.value == 1
        ):
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
                    if isinstance(slice_node, (ast.Slice, ast.Constant)):
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


def scan_secrets(relative_path: Path, source: str) -> list[Finding]:
    """Scan file content for leaked private keys, credentials, and personal paths."""
    findings: list[Finding] = []
    lines = source.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if SECRET_PRIVATE_KEY_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SEC001",
                    "critical",
                    "Unencrypted private key material detected in repository source.",
                )
            )
        if SECRET_API_KEY_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SEC001",
                    "critical",
                    "Hardcoded API token or credential detected.",
                )
            )
        if SECRET_PERSONAL_PATH_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SEC002",
                    "critical",
                    "Personal absolute filesystem path detected; sanitize to repo-relative.",
                )
            )
    return findings


def scan_python_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [
            Finding(
                relative_path.as_posix(),
                1,
                "FMT001",
                "critical",
                "File is not valid UTF-8 text.",
            )
        ]
    findings: list[Finding] = scan_secrets(relative_path, source)
    try:
        tree = ast.parse(source, filename=str(relative_path))
    except SyntaxError as exc:
        findings.append(
            Finding(
                path=relative_path.as_posix(),
                line=exc.lineno or 1,
                rule="PY000",
                severity="critical",
                message=f"Python syntax error: {exc.msg}",
            )
        )
        return findings

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
        if relative_path.name.endswith(
            PHYSICAL_SUFFIX
        ) and SELF_DECLARED_BACKEND_RE.search(line):
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


def scan_cpp_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [
            Finding(
                relative_path.as_posix(),
                1,
                "FMT001",
                "critical",
                "File is not valid UTF-8 text.",
            )
        ]
    findings: list[Finding] = scan_secrets(relative_path, source)
    lines = source.splitlines()

    for line_number, line in enumerate(lines, start=1):
        if CPP_TRIVIAL_ASSERT_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "CPP001",
                    "critical",
                    "Trivial assertion `assert(true)` or `static_assert(true)` cannot validate behavior.",
                )
            )
        if HARDCODED_PASS_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "CPP004",
                    "critical",
                    "Hardcoded passing count is forbidden in C/C++ sources.",
                )
            )
        if CPP_PREPROCESSOR_FALLBACK_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "CPP003",
                    "critical",
                    "Preprocessor-controlled host/CPU fallback is forbidden in physical paths.",
                )
            )
        if CPP_UNSAFE_MEMCPY_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "CPP005",
                    "warning",
                    "Zero-sized or unsafe memcpy detected; verify buffer bounds.",
                )
            )

    if CPP_CATCH_FALLBACK_RE.search(source):
        findings.append(
            Finding(
                relative_path.as_posix(),
                1,
                "CPP002",
                "critical",
                "Catch block calling host/CPU fallback is forbidden.",
            )
        )
    return findings


def load_evidence_manifest_hashes() -> dict[str, str]:
    manifest_file = REPO_ROOT / "docs" / "pqc_dr2_evidence_20260818" / "SHA256SUMS"
    if not manifest_file.is_file():
        return {}
    hashes: dict[str, str] = {}
    for line in manifest_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            h, p = parts
            p = p.lstrip("./")
            hashes[f"docs/pqc_dr2_evidence_20260818/{p}"] = h
    return hashes


EVIDENCE_MANIFEST_HASHES = load_evidence_manifest_hashes()


def scan_script_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [
            Finding(
                relative_path.as_posix(),
                1,
                "FMT001",
                "critical",
                "File is not valid UTF-8 text.",
            )
        ]
    findings: list[Finding] = scan_secrets(relative_path, source)

    norm = relative_path.as_posix()
    if norm in EVIDENCE_MANIFEST_HASHES:
        expected = EVIDENCE_MANIFEST_HASHES[norm]
        actual = sha256_file(target)
        if actual != expected:
            findings.append(
                Finding(
                    norm,
                    1,
                    "EVID001",
                    "critical",
                    f"Evidence file '{norm}' checksum mismatch against SHA256SUMS manifest: expected {expected}, got {actual}",
                )
            )
        return findings

    lines = source.splitlines()

    for line_number, line in enumerate(lines, start=1):
        if SCRIPT_IGNORED_EXIT_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SH001",
                    "critical",
                    "Process exit codes must not be masked with zero or ignored.",
                )
            )
        if SCRIPT_SILENTLY_CONTINUE_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SH002",
                    "critical",
                    "ErrorAction SilentlyContinue is forbidden in test and validation paths.",
                )
            )
        if HARDCODED_PASS_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SH004",
                    "critical",
                    "Hardcoded PASS banner is forbidden in validation scripts.",
                )
            )
        if SCRIPT_DESTRUCTIVE_CMD_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "SH005",
                    "critical",
                    "Unsafely destructive system command detected.",
                )
            )

    if SCRIPT_GENERIC_PYTHON_FALLBACK_RE.search(source):
        findings.append(
            Finding(
                relative_path.as_posix(),
                1,
                "SH003",
                "critical",
                "Silent fallback from ironenv to generic Python is forbidden.",
            )
        )
    return findings


def scan_mlir_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    source = target.read_text(encoding="utf-8", errors="replace")
    findings = scan_secrets(relative_path, source)
    for line_number, line in enumerate(source.splitlines(), start=1):
        if HARDCODED_PASS_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "MLIR001",
                    "critical",
                    "Hardcoded pass banner forbidden in MLIR artifacts.",
                )
            )
    return findings


def scan_cmake_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    source = target.read_text(encoding="utf-8", errors="replace")
    findings = scan_secrets(relative_path, source)
    for line_number, line in enumerate(source.splitlines(), start=1):
        if HARDCODED_PASS_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "CMAKE001",
                    "critical",
                    "Hardcoded pass banner forbidden in CMake configurations.",
                )
            )
    return findings


def scan_structured_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    source = target.read_text(encoding="utf-8", errors="replace")
    findings = scan_secrets(relative_path, source)

    if relative_path.suffix.lower() == ".json":
        try:
            json.loads(source)
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    exc.lineno,
                    "FMT001",
                    "critical",
                    f"Malformed JSON syntax: {exc.msg}",
                )
            )
    return findings


def validate_claim_provenance(
    relative_path: Path,
    claim_line_num: int,
    claim_line_text: str,
    prov: ClaimProvenance,
) -> list[Finding]:
    findings: list[Finding] = []
    norm_path = relative_path.as_posix()

    if prov.status not in {"VERIFIED", "UNVERIFIED", "HISTORICAL"}:
        return [
            Finding(
                norm_path,
                prov.line,
                "DOC002",
                "critical",
                f"Invalid claim provenance status '{prov.status}'; must be VERIFIED, UNVERIFIED, or HISTORICAL.",
            )
        ]

    # Validate commit SHA if provided
    if prov.commit and not COMMIT_RE.match(prov.commit):
        findings.append(
            Finding(
                norm_path,
                prov.line,
                "DOC002",
                "critical",
                f"Malformed or abbreviated commit SHA '{prov.commit}' in claim provenance; must be 40-character hex SHA.",
            )
        )

    # Validate evidence path if provided
    if prov.evidence:
        raw_ev = prov.evidence.strip()
        is_abs = (
            Path(raw_ev).is_absolute()
            or bool(re.match(r"^[a-zA-Z]:[/\\]", raw_ev))
            or raw_ev.startswith(("/", "\\"))
        )
        if ".." in Path(raw_ev).parts or is_abs:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    f"Evidence path '{raw_ev}' escapes repository root.",
                )
            )
        else:
            ev_file = (REPO_ROOT / raw_ev).resolve()
            try:
                ev_file.relative_to(REPO_ROOT.resolve())
                if not ev_file.is_file():
                    findings.append(
                        Finding(
                            norm_path,
                            prov.line,
                            "DOC002",
                            "critical",
                            f"Stated evidence file '{raw_ev}' does not exist.",
                        )
                    )
            except ValueError:
                findings.append(
                    Finding(
                        norm_path,
                        prov.line,
                        "DOC002",
                        "critical",
                        f"Evidence path '{raw_ev}' escapes repository root.",
                    )
                )

    if prov.status == "VERIFIED":
        if not prov.evidence:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "status=VERIFIED requires a valid 'evidence' path.",
                )
            )
        if not prov.commit:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "status=VERIFIED requires a 40-character 'commit' SHA.",
                )
            )
        if not prov.classification:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "status=VERIFIED requires an evidence 'classification'.",
                )
            )

        if prov.evidence:
            raw_ev = prov.evidence.strip()
            is_abs = (
                Path(raw_ev).is_absolute()
                or bool(re.match(r"^[a-zA-Z]:[/\\]", raw_ev))
                or raw_ev.startswith(("/", "\\"))
            )
            if not (".." in Path(raw_ev).parts or is_abs):
                ev_file = (REPO_ROOT / raw_ev).resolve()
                if ev_file.is_file():
                    manifest_data = None
                    try:
                        with ev_file.open("r", encoding="utf-8") as handle:
                            content = handle.read()
                        if not content.strip():
                            raise ValueError("Evidence file is empty")
                        manifest_data = json.loads(content)
                        if not isinstance(manifest_data, dict):
                            raise TypeError("Evidence file must be a JSON object")
                    except (
                        json.JSONDecodeError,
                        OSError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        findings.append(
                            Finding(
                                norm_path,
                                prov.line,
                                "DOC002",
                                "critical",
                                f"Evidence file '{raw_ev}' is empty or malformed JSON: {exc}",
                            )
                        )

                    if manifest_data is not None:
                        # 1. Validate evidence invariants and verify artifact hashes
                        manifest_class = manifest_data.get("evidence_class")
                        if (
                            manifest_class == "BIT_EXACT_PHYSICAL_SILICON"
                            or prov.classification == "BIT_EXACT_PHYSICAL_SILICON"
                        ):
                            evidence_errors = validate_evidence(
                                manifest_data, ev_file, check_files=True
                            )
                            if evidence_errors:
                                findings.append(
                                    Finding(
                                        norm_path,
                                        prov.line,
                                        "DOC002",
                                        "critical",
                                        f"Evidence validation failed for '{raw_ev}': {'; '.join(evidence_errors[:3])}",
                                    )
                                )
                        elif manifest_class in {
                            "HOST_REFERENCE",
                            "CONTRACT",
                            "COMPILE_ONLY",
                        }:
                            if manifest_data.get("schema_version") != 1:
                                findings.append(
                                    Finding(
                                        norm_path,
                                        prov.line,
                                        "DOC002",
                                        "critical",
                                        f"Evidence manifest '{raw_ev}' schema_version must equal 1",
                                    )
                                )
                        else:
                            findings.append(
                                Finding(
                                    norm_path,
                                    prov.line,
                                    "DOC002",
                                    "critical",
                                    f"Evidence manifest '{raw_ev}' has invalid evidence_class '{manifest_class}'",
                                )
                            )

                        # 2. Verify commit binding
                        manifest_commit = (
                            manifest_data.get("repository", {}).get("commit")
                            if isinstance(manifest_data.get("repository"), dict)
                            else None
                        )
                        if manifest_commit != prov.commit:
                            findings.append(
                                Finding(
                                    norm_path,
                                    prov.line,
                                    "DOC002",
                                    "critical",
                                    f"Evidence file '{raw_ev}' is bound to commit '{manifest_commit}' but claim specifies commit '{prov.commit}'.",
                                )
                            )

                        # 3. Verify classification matches
                        if prov.classification != manifest_class:
                            findings.append(
                                Finding(
                                    norm_path,
                                    prov.line,
                                    "DOC002",
                                    "critical",
                                    f"Claim classification '{prov.classification}' disagrees with evidence manifest '{manifest_class}'.",
                                )
                            )

        # Check commit existence in repository history
        if prov.commit and COMMIT_RE.match(prov.commit):
            try:
                commit_check = subprocess.run(
                    ["git", "cat-file", "-e", f"{prov.commit}^{{commit}}"],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    check=False,
                )
                if commit_check.returncode != 0:
                    findings.append(
                        Finding(
                            norm_path,
                            prov.line,
                            "DOC002",
                            "critical",
                            f"Referenced commit '{prov.commit}' does not exist in repository history.",
                        )
                    )
            except (subprocess.CalledProcessError, OSError) as exc:
                findings.append(
                    Finding(
                        norm_path,
                        prov.line,
                        "DOC002",
                        "critical",
                        f"Failed to verify commit '{prov.commit}' in repository history: {exc}",
                    )
                )

        # Enforce physical claim restrictions while PHYSICAL-DISPATCH-CORROBORATION is OPEN
        is_physical_claim = bool(
            re.search(
                r"\[VERIFIED PHYSICAL SILICON\]|\bphysically verified\b|\bexecuted on silicon\b|\bon[- ]tile silicon\b|\bphysical silicon\b|\bhardware verified\b",
                claim_line_text,
                re.IGNORECASE,
            )
        )
        if is_physical_claim:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "Physical silicon claim cannot be authorized: independent physical dispatch corroboration is unavailable while PHYSICAL-DISPATCH-CORROBORATION remains OPEN.",
                )
            )
            if prov.classification != "BIT_EXACT_PHYSICAL_SILICON":
                findings.append(
                    Finding(
                        norm_path,
                        prov.line,
                        "DOC002",
                        "critical",
                        f"Evidence classification '{prov.classification}' cannot authorize a VERIFIED physical silicon claim; BIT_EXACT_PHYSICAL_SILICON is required.",
                    )
                )
        elif prov.classification == "BIT_EXACT_PHYSICAL_SILICON":
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "status=VERIFIED cannot authorize BIT_EXACT_PHYSICAL_SILICON classification while PHYSICAL-DISPATCH-CORROBORATION remains OPEN.",
                )
            )

    elif prov.status == "HISTORICAL":
        unauthorized_patterns = (
            (
                r"\[VERIFIED PHYSICAL SILICON\]|\bphysically verified\b",
                "VERIFIED PHYSICAL SILICON",
            ),
            (r"\bstandards compliant\b", "standards compliant"),
            (r"\bconstant[- ]time\b", "constant time"),
            (r"\bside[- ]channel resistant\b", "side-channel resistant"),
        )
        for pat, desc in unauthorized_patterns:
            if re.search(pat, claim_line_text, re.IGNORECASE):
                findings.append(
                    Finding(
                        norm_path,
                        prov.line,
                        "DOC002",
                        "critical",
                        f"status=HISTORICAL cannot authorize '{desc}' claim; downgrade claim text or prove with fresh physical evidence.",
                    )
                )
        if not prov.evidence and not prov.source:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "status=HISTORICAL requires 'evidence' or 'source' reference.",
                )
            )
        elif not any(f.severity == "critical" for f in findings if f.line == prov.line):
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC003",
                    "warning",
                    f"Historical claim recorded: {claim_line_text.strip()[:80]}",
                )
            )

    elif prov.status == "UNVERIFIED":
        if "[VERIFIED PHYSICAL SILICON]" in claim_line_text:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC002",
                    "critical",
                    "Claim text '[VERIFIED PHYSICAL SILICON]' contradicts status=UNVERIFIED; downgrade claim text.",
                )
            )
        else:
            findings.append(
                Finding(
                    norm_path,
                    prov.line,
                    "DOC003",
                    "warning",
                    f"Unverified claim acknowledged: {claim_line_text.strip()[:80]}",
                )
            )

    return findings


def is_claim_line(lines: list[str], idx: int) -> bool:
    line = lines[idx]
    if not DOC_STRONG_CLAIM_RE.search(line):
        return False
    line_lower = line.lower()
    disclaimers = (
        "does not claim",
        "never claim",
        "never use",
        "no performance",
        "without bounded",
        "without evidence",
        "are separate evidence levels",
        "separate evidence levels",
        "is forbidden",
        "are forbidden",
        "no claim",
        "cannot be claimed",
        "prohibit",
        "forbidden",
        "treat skipped",
        "where the claim depends",
        "statements are not equivalent",
        "model",
        "0 independently physically verified",
        "0 physically verified",
        "0 verified",
        "pending physical dispatch corroboration",
        "pending physical dispatch",
        "makes no constant-time",
        "no constant-time",
        "non-constant-time",
        "no side-channel",
        "not proven",
        "does not prove",
        "is not evidence",
        "not silicon validation",
        "not silicon evidence",
        "no hardware",
        "no physical",
        "do not claim",
        "do not use",
        "do not allow",
        "not claimed",
        "are not claimed",
        "is not claimed",
        "does not inherit",
        "operator-retained assertion",
        "operator-supplied",
    )
    if any(d in line_lower for d in disclaimers):
        return False
    if re.search(
        r"(?:physically verified|verified)\s*(?:gates|cases|suites)?\s*:\s*0\b",
        line_lower,
    ):
        return False

    stripped = line.strip()
    return not any(
        stripped.startswith(prefix)
        for prefix in (
            "- Use ",
            "- Inspect ",
            "- Enforce ",
            "- Verify ",
            "- Validate ",
            "- Prohibit ",
            "- [ ] ",
        )
    )


def scan_markdown_file(relative_path: Path) -> list[Finding]:
    if is_policy_exempt(relative_path):
        return []
    target = REPO_ROOT / relative_path
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [
            Finding(
                relative_path.as_posix(),
                1,
                "FMT001",
                "critical",
                "File is not valid UTF-8 text.",
            )
        ]
    findings: list[Finding] = scan_secrets(relative_path, source)
    lines = source.splitlines()

    # Pre-parse all claim annotations by line number
    annotations: dict[int, ClaimProvenance] = {}
    for idx, line in enumerate(lines, start=1):
        parsed = parse_claim_provenance(idx, line)
        if parsed:
            annotations[idx] = parsed

    # Track consumed annotation line numbers so one annotation only binds to one claim
    used_annotations: set[int] = set()

    for line_number, line in enumerate(lines, start=1):
        if not is_claim_line(lines, line_number - 1):
            continue

        # Look for adjacent annotation: same line, line - 1, or line + 1
        matched_annotation_line: int | None = None
        for candidate in (line_number, line_number - 1, line_number + 1):
            if candidate in annotations and candidate not in used_annotations:
                matched_annotation_line = candidate
                break

        if matched_annotation_line is not None:
            used_annotations.add(matched_annotation_line)
            prov = annotations[matched_annotation_line]
            val_findings = validate_claim_provenance(
                relative_path, line_number, line, prov
            )
            findings.extend(val_findings)
        else:
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "DOC001",
                    "critical",
                    f"Strong unverified claim requires adjacent [CLAIM-PROVENANCE: ...]: {line.strip()[:80]}",
                )
            )

    return findings


def scan_file(relative_path: Path) -> list[Finding]:
    """Dispatch scanning to the appropriate language scanner."""
    resolved = (REPO_ROOT / relative_path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return [
            Finding(
                relative_path.as_posix(),
                1,
                "PATH001",
                "critical",
                "Path traversal escapes repository root.",
            )
        ]

    suffix = relative_path.suffix.lower()
    name = relative_path.name
    if suffix == ".py" or name == "install":
        return scan_python_file(relative_path)
    if suffix in {".c", ".cc", ".cpp", ".h", ".hpp"}:
        return scan_cpp_file(relative_path)
    if suffix in {".ps1", ".sh"}:
        return scan_script_file(relative_path)
    if suffix == ".mlir":
        return scan_mlir_file(relative_path)
    if suffix == ".cmake" or name == "CMakeLists.txt":
        return scan_cmake_file(relative_path)
    if suffix in {".json", ".yml", ".yaml"}:
        return scan_structured_file(relative_path)
    if suffix == ".md":
        return scan_markdown_file(relative_path)
    if name == ".editorconfig" or suffix == ".editorconfig":
        return scan_script_file(relative_path)
    return []


def scan_paths(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        findings.extend(scan_file(path))
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
        raise TypeError("top-level JSON value must be an object")
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
    if (
        not isinstance(dispatches, int)
        or isinstance(dispatches, bool)
        or dispatches < 1
    ):
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
                errors.append(
                    f"`comparisons[{index}]` expected and actual hashes differ"
                )
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
            if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(
                expected_hash
            ):
                errors.append(f"`artifacts[{index}].sha256` is invalid")
                continue
            if check_files:
                artifact_path = (manifest_path.parent / relative).resolve()
                try:
                    artifact_path.relative_to(manifest_path.parent.resolve())
                except ValueError:
                    errors.append(
                        f"`artifacts[{index}].path` escapes the evidence directory"
                    )
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
