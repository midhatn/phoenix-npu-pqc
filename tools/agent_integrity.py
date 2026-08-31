"""Shared integrity and policy checks for repository changes across all languages."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def get_canonical_gate_metadata():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from run_all_silicon_tests import EXTENSION_GATES, GATES

        canonical_map = {g.gate_id.upper(): g for g in GATES}
        canonical_order = [g.gate_id.upper() for g in GATES]
        extension_map = {g.gate_id.upper(): g for g in EXTENSION_GATES}
        return canonical_map, canonical_order, extension_map
    except ImportError:
        return {}, [], {}


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
    ".bat",
    ".cmd",
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
CPP_KNOWN_VECTOR_RE = re.compile(
    r"\b(?:request_id\s*==\s*0x[0-9a-fA-F]+|0x[0-9a-fA-F]+\s*==\s*request_id|"
    r"tc_id\s*==\s*\d+|\d+\s*==\s*tc_id|"
    r"case_id\s*==\s*\d+|\d+\s*==\s*case_id|"
    r"test_id\s*==\s*\d+|\d+\s*==\s*test_id|"
    r"known_vector|known_hash|known_seed|kKnownAcvpSeed)\b|"
    r"\bswitch\s*\([^)]*(?:request_id|tc_id|case_id|test_id)[^)]*\)\s*\{[^}]*\bcase\s+(?:0x[0-9a-fA-F]+|\d+)\s*:",
    re.IGNORECASE | re.DOTALL,
)
CPP_FINGERPRINT_MATCH_RE = re.compile(
    r"\bif\s*\([^)]*(?:(?:sha256|sha3_256|hash)\s*\([^)]*\)\s*==\s*(?:known_hash|0x[0-9a-fA-F]+|\"[0-9a-fA-F]{16,64}\")|"
    r"(?:known_hash|0x[0-9a-fA-F]+|\"[0-9a-fA-F]{16,64}\")\s*==\s*(?:sha256|sha3_256|hash)\s*\([^)]*\))[^)]*\)",
    re.IGNORECASE | re.DOTALL,
)
CPP_EXPECTED_OUTPUT_COPY_RE = re.compile(
    r"\b(?:memcpy|copy_bytes)\s*\(\s*[^,]+,\s*(?:expected_output|kExpectedOutput|expected_buf|oracle_output|expected)\b|"
    r"\bstd::copy\s*\(\s*(?:expected_output|kExpectedOutput|expected_buf|oracle_output|expected)\b",
    re.IGNORECASE | re.DOTALL,
)
CPP_HOST_FALLBACK_CALL_RE = re.compile(
    r"\b(?:run_host_fallback|host_reference_fallback|cpu_fallback)\s*\(",
    re.IGNORECASE | re.DOTALL,
)

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

# Host, driver, and system integrity mutation patterns (bounded CLI rules)
HOST_CLI_MUTATION_RULES = [
    (
        "HOST001",
        "critical",
        re.compile(
            r"\bpnputil(?:\.exe)?[\s,\"']+(?:[^\r\n;|]+?[\s,\"']+)?(?:[/-](?:add-driver|delete-driver|install-driver|import-driver|i\s+-[aA]|[aA]\s+-[iI]|[iI][aA]|[aA][iI]|[dD]))\b|"
            r"\bdevcon(?:\.exe)?[\s,\"']+(?:[^\r\n;|]+?[\s,\"']+)?(?:install|remove|restart|disable|enable|update|updateni|reboot|rescan)\b|"
            r"\bdism(?:\.exe)?[\s,\"']+[^\r\n;|]*?/(?:add-driver|remove-driver|import-driver)\b",
            re.IGNORECASE,
        ),
        "Host or driver mutation command is forbidden (pnputil, devcon, or driver-changing DISM).",
    ),
    (
        "HOST002",
        "critical",
        re.compile(
            r"\bStart-Process\s+[^\r\n;|]*?-Verb\s+['\"]?RunAs['\"]?|"
            r"\brunas(?:\.exe)?[\s,\"']+[^\r\n;|]*?[/-]user\s*:\s*|"
            r"\bsudo\s+",
            re.IGNORECASE,
        ),
        "Administrator elevation or privilege escalation command is forbidden.",
    ),
    (
        "HOST003",
        "critical",
        re.compile(
            r"\bsc(?:\.exe)?[\s,\"']+(?:[^\r\n;|]+?[\s,\"']+)?(?:create|delete|config)\b|"
            r"\b(?:New-Service|Set-Service|Remove-Service)\b|"
            r"\breg(?:\.exe)?[\s,\"']+(?:[^\r\n;|]+?[\s,\"']+)?(?:add|delete|import|restore)[\s,\"']+(?:HKLM|HKEY_LOCAL_MACHINE)\b|"
            r"\b(?:Set-ItemProperty|New-Item|Remove-Item|New-ItemProperty|Remove-ItemProperty|Set-Item|Clear-ItemProperty)\s+[^\r\n;|]*?(?:HKLM:|Registry::HKEY_LOCAL_MACHINE|HKLM\\|HKEY_LOCAL_MACHINE\\)",
            re.IGNORECASE,
        ),
        "Machine-wide registry or driver/system service mutation is forbidden.",
    ),
    (
        "HOST004",
        "critical",
        re.compile(
            r"\bbcdedit(?:\.exe)?[\s,\"']+(?:[^\r\n;|]+?[\s,\"']+)?(?:[/-](?:set|deletevalue|create|delete|default|bootdebug|debug|timeout))\b",
            re.IGNORECASE,
        ),
        "Boot configuration (bcdedit) mutation is forbidden.",
    ),
    (
        "HOST007",
        "critical",
        re.compile(
            r"\bpowershell(?:\.exe)?\s+[^\r\n;|]*?(?:-[eE](?:nc(?:odedcommand)?)?)\s+[A-Za-z0-9+/=]{10,}|"
            r"\b(?:Invoke-Expression|iex)\b[^\r\n;|]*?\b(?:DownloadString|DownloadData|DownloadFile|Invoke-WebRequest|iwr|Invoke-RestMethod|irm)\b|"
            r"\b(?:curl|wget)\b[^\r\n;|]*?\|\s*(?:sh|bash|powershell|pwsh|cmd)\b",
            re.IGNORECASE,
        ),
        "Obfuscated execution, encoded PowerShell, or download-and-execute pattern is forbidden.",
    ),
]


# Direct native dangerous API patterns (C/C++ and Python)
HOST_NATIVE_API_RULES = [
    (
        "HOST005",
        "critical",
        re.compile(
            r"\b(?:SetupCopyOEMInf[AW]?|DiInstallDriver[AW]?|UpdateDriverForPlugAndPlayDevices[AW]?|NtLoadDriver|ZwLoadDriver|NtUnloadDriver|ZwUnloadDriver)\s*\(",
            re.IGNORECASE,
        ),
        "Native driver installation or driver-loading API is forbidden.",
    ),
    (
        "HOST006",
        "critical",
        re.compile(
            r"\b(?:WriteProcessMemory|NtWriteVirtualMemory|ZwWriteVirtualMemory|CreateRemoteThread|NtCreateThreadEx|ZwCreateThreadEx|SetWindowsHookEx[AW]?|DetourAttach|DetourTransactionBegin|DetourUpdateThread|DetourDetach)\s*\(",
            re.IGNORECASE,
        ),
        "Process injection, cross-process memory tampering, or API/syscall hooking is forbidden.",
    ),
]

# C/C++ process-launching sink pattern
CPP_PROCESS_SINK_RE = re.compile(
    r"\b(?:system|_wsystem|_popen|popen|ShellExecute[AW]?|ShellExecuteEx[AW]?|CreateProcess[AW]?)\s*\(((?:[^;)\n]|[\r\n]){1,4096}?)\)",
    re.IGNORECASE,
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
    r"\bverified on (?:phoenix\s+)?(?:aie2\s+)?hardware\b|"
    r"\bconfirmed on silicon\b|"
    r"\bpassed on (?:the\s+)?(?:physical\s+)?npu\b|"
    r"\bhardware accelerated\b|"
    r"\bstandards compliant\b|"
    r"\bconstant[- ]time\b|"
    r"\bside[- ]channel resistant\b|"
    r"\bproduction ready\b|"
    r"\b\d+\s*/\s*\d+\s+(?:TESTS?\s+)?PASS(?:ED|ING)?\b"
)
DOC_PROHIBITED_TERMINOLOGY_RE = re.compile(
    r"\b(?:public|committed|deterministic)\s+.*(?:hidden vectors?|hidden inputs?)\b|"
    r"\bhidden\s+(?:deterministic|public)\b|"
    r"\b(?:zero|0)\s+scanner\s+findings?\s+proves?\s+(?:cryptographic\s+correctness|semantic\s+correctness|correctness)\b|"
    r"\bscanner\s+(?:passed|success)\s+(?:proves|guarantees)\s+(?:cryptographic|semantic)\s+correctness\b|"
    r"\b(?:warm\s+cache\s+fresh\s+(?:compile|build)|cache\s+hit\s+described\s+as\s+fresh|cache\s+hit\s+fresh\s+(?:compile|build))\b",
    re.IGNORECASE,
)
DOC_REPO_ROOT_CITATION_RE = re.compile(
    r"(?i)evidence source\s*:\s*https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+/?\s*$"
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

        # Check process-launching sinks for CLI mutation commands
        c_name = call_name(node.func)
        c_name_lower = c_name.lower()
        is_sink = any(
            c_name_lower == sink or c_name_lower.endswith(f".{sink}")
            for sink in (
                "subprocess.run",
                "subprocess.popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
                "os.system",
                "os.popen",
            )
        )
        if is_sink and node.args:
            arg0 = node.args[0]
            cmd_str = ""
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                cmd_str = arg0.value
            elif isinstance(arg0, (ast.List, ast.Tuple)):
                tokens = []
                for elt in arg0.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        tokens.append(elt.value)
                cmd_str = " ".join(tokens)
            if cmd_str:
                for rule, severity, pattern, message in HOST_CLI_MUTATION_RULES:
                    if pattern.search(cmd_str):
                        self.add(node, rule, severity, message)

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
    for rule, severity, pattern, message in HOST_NATIVE_API_RULES:
        for m in pattern.finditer(source):
            line_no = source[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_no,
                    rule,
                    severity,
                    message,
                )
            )

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


def strip_cpp_comments(source: str) -> str:
    """Replace C/C++ comments (// and /* */) with spaces, preserving string literals, line breaks, and offsets."""
    chars = list(source)
    n = len(chars)
    i = 0
    in_string = False
    quote_char = ""
    while i < n:
        if in_string:
            if chars[i] == "\\":
                i += 2
                continue
            if chars[i] == quote_char:
                in_string = False
            i += 1
            continue

        if chars[i] in ('"', "'"):
            in_string = True
            quote_char = chars[i]
            i += 1
            continue

        if i + 1 < n and chars[i] == "/" and chars[i + 1] == "/":
            chars[i] = " "
            chars[i + 1] = " "
            i += 2
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
        elif i + 1 < n and chars[i] == "/" and chars[i + 1] == "*":
            chars[i] = " "
            chars[i + 1] = " "
            i += 2
            while i < n and not (chars[i] == "*" and chars[i + 1] == "/"):
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < n and chars[i] == "*" and chars[i + 1] == "/":
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
        else:
            i += 1
    return "".join(chars)


def strip_hash_comments(source: str) -> str:
    """Replace '#' and '<# #>' comments with spaces, preserving string literals, line breaks, and offsets."""
    chars = list(source)
    n = len(chars)
    i = 0
    in_single_quote = False
    in_double_quote = False
    while i < n:
        c = chars[i]
        if c == "\\":
            i += 2
            continue
        if c == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            i += 1
            continue
        if c == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue
        if c == "#" and not in_single_quote and not in_double_quote:
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        if (
            not in_single_quote
            and not in_double_quote
            and i + 1 < n
            and chars[i] == "<"
            and chars[i + 1] == "#"
        ):
            chars[i] = " "
            chars[i + 1] = " "
            i += 2
            while i < n and not (chars[i] == "#" and chars[i + 1] == ">"):
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < n and chars[i] == "#" and chars[i + 1] == ">":
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
            continue
        i += 1
    return "".join(chars)


def assemble_logical_commands(
    relative_path: Path,
    source: str,
    language: str,
    max_lines: int = 32,
    max_chars: int = 4096,
) -> tuple[list[tuple[int, str]], list[Finding]]:
    """Assemble discrete logical commands from script or workflow source.

    Returns (commands, overflow_findings).
    Fails closed with a critical finding if a logical command exceeds max_lines or max_chars.
    """
    commands: list[tuple[int, str]] = []
    findings: list[Finding] = []
    norm_path = relative_path.as_posix()

    if language in {"shell", "script", "sh"}:
        sanitized = strip_hash_comments(source)
        lines = sanitized.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            line_str = lines[i]
            line_num = i + 1
            if not line_str.strip():
                i += 1
                continue

            if len(line_str) > max_chars:
                findings.append(
                    Finding(
                        norm_path,
                        line_num,
                        "HOST001",
                        "critical",
                        f"Command continuation exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                    )
                )
                i += 1
                continue

            accum = [line_str.rstrip("\r\n")]
            has_continuation = accum[0].rstrip().endswith("\\")
            if has_continuation:
                accum[0] = accum[0].rstrip()[:-1]

            start_line = line_num
            line_count = 1
            while has_continuation and i + 1 < n:
                i += 1
                line_count += 1
                curr_line = lines[i].rstrip("\r\n")
                if curr_line.rstrip().endswith("\\"):
                    accum.append(curr_line.rstrip()[:-1])
                    has_continuation = True
                else:
                    accum.append(curr_line)
                    has_continuation = False

                total_chars = sum(len(s) for s in accum)
                if line_count > max_lines or total_chars > max_chars:
                    findings.append(
                        Finding(
                            norm_path,
                            start_line,
                            "HOST001",
                            "critical",
                            f"Command continuation exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                        )
                    )
                    break

            joined = " ".join(part.strip() for part in accum if part.strip())
            if joined:
                for sub_cmd in joined.split(";"):
                    sub_cmd_clean = sub_cmd.strip()
                    if sub_cmd_clean:
                        commands.append((start_line, sub_cmd_clean))
            i += 1

    elif language in {"powershell", "ps1"}:
        sanitized = strip_hash_comments(source)
        lines = sanitized.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            line_str = lines[i]
            line_num = i + 1
            if not line_str.strip():
                i += 1
                continue

            if len(line_str) > max_chars:
                findings.append(
                    Finding(
                        norm_path,
                        line_num,
                        "HOST001",
                        "critical",
                        f"Command continuation exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                    )
                )
                i += 1
                continue

            accum = [line_str.rstrip("\r\n")]
            has_continuation = accum[0].rstrip().endswith("`")
            if has_continuation:
                accum[0] = accum[0].rstrip()[:-1]

            start_line = line_num
            line_count = 1
            while has_continuation and i + 1 < n:
                i += 1
                line_count += 1
                curr_line = lines[i].rstrip("\r\n")
                if curr_line.rstrip().endswith("`"):
                    accum.append(curr_line.rstrip()[:-1])
                    has_continuation = True
                else:
                    accum.append(curr_line)
                    has_continuation = False

                total_chars = sum(len(s) for s in accum)
                if line_count > max_lines or total_chars > max_chars:
                    findings.append(
                        Finding(
                            norm_path,
                            start_line,
                            "HOST001",
                            "critical",
                            f"Command continuation exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                        )
                    )
                    break

            joined = " ".join(part.strip() for part in accum if part.strip())
            if joined:
                for sub_cmd in joined.split(";"):
                    sub_cmd_clean = sub_cmd.strip()
                    if sub_cmd_clean:
                        commands.append((start_line, sub_cmd_clean))
            i += 1

    elif language in {"yaml", "yml", "structured"}:
        sanitized = strip_hash_comments(source)
        lines = sanitized.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            line_str = lines[i]
            line_num = i + 1
            run_match = re.search(r"^\s*(?:-\s*)?run\s*:\s*(.*)$", line_str)
            if run_match:
                start_line = line_num
                val = run_match.group(1).strip()
                is_literal = bool(re.match(r"^\|[+-]?\d*$", val))
                is_folded = bool(re.match(r"^>[+-]?\d*$", val))
                if is_literal or is_folded:
                    indent = len(line_str) - len(line_str.lstrip())
                    block_lines: list[tuple[int, str]] = []
                    j = i + 1
                    while j < n:
                        curr = lines[j]
                        curr_indent = len(curr) - len(curr.lstrip())
                        if curr.strip() and curr_indent <= indent:
                            break
                        block_lines.append((j + 1, curr))
                        j += 1
                    i = j - 1

                    if is_literal:
                        k = 0
                        num_block_lines = len(block_lines)
                        while k < num_block_lines:
                            orig_ln, b_line = block_lines[k]
                            if not b_line.strip():
                                k += 1
                                continue

                            accum = [b_line.rstrip("\r\n")]
                            cmd_start_line = orig_ln
                            has_continuation = accum[0].rstrip().endswith("\\")
                            if has_continuation:
                                accum[0] = accum[0].rstrip()[:-1]

                            cmd_line_count = 1
                            while has_continuation and k + 1 < num_block_lines:
                                k += 1
                                cmd_line_count += 1
                                next_orig_ln, next_b_line = block_lines[k]
                                curr_l = next_b_line.rstrip("\r\n")
                                if curr_l.rstrip().endswith("\\"):
                                    accum.append(curr_l.rstrip()[:-1])
                                    has_continuation = True
                                else:
                                    accum.append(curr_l)
                                    has_continuation = False

                                total_chars = sum(len(s) for s in accum)
                                if (
                                    cmd_line_count > max_lines
                                    or total_chars > max_chars
                                ):
                                    findings.append(
                                        Finding(
                                            norm_path,
                                            cmd_start_line,
                                            "HOST001",
                                            "critical",
                                            f"Command continuation exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                                        )
                                    )
                                    break

                            joined = " ".join(
                                part.strip() for part in accum if part.strip()
                            )
                            if joined:
                                for sub_cmd in joined.split(";"):
                                    sub_cmd_clean = sub_cmd.strip()
                                    if sub_cmd_clean:
                                        commands.append((cmd_start_line, sub_cmd_clean))
                            k += 1

                    elif is_folded:
                        non_empty_block = [
                            (ln, line) for ln, line in block_lines if line.strip()
                        ]
                        folded_line_count = len(non_empty_block)
                        total_chars = sum(
                            len(line.strip()) for _, line in non_empty_block
                        )
                        if folded_line_count > max_lines or total_chars > max_chars:
                            findings.append(
                                Finding(
                                    norm_path,
                                    start_line,
                                    "HOST001",
                                    "critical",
                                    f"YAML folded run block exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                                )
                            )
                        else:
                            joined = " ".join(
                                line.strip()
                                for _, line in non_empty_block
                                if line.strip()
                            )
                            if joined:
                                for sub_cmd in joined.split(";"):
                                    sub_cmd_clean = sub_cmd.strip()
                                    if sub_cmd_clean:
                                        commands.append((start_line, sub_cmd_clean))
                else:
                    if val:
                        if len(val) > max_chars:
                            findings.append(
                                Finding(
                                    norm_path,
                                    start_line,
                                    "HOST001",
                                    "critical",
                                    f"Command continuation exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                                )
                            )
                        else:
                            for sub_cmd in val.split(";"):
                                sub_cmd_clean = sub_cmd.strip()
                                if sub_cmd_clean:
                                    commands.append((start_line, sub_cmd_clean))
            i += 1

    elif language in {"cmake"}:
        sanitized = strip_hash_comments(source)
        lines = sanitized.splitlines()
        cmake_exec_re = re.compile(
            r"\b(execute_process|add_custom_command|add_custom_target)\s*\(",
            re.IGNORECASE,
        )
        for line_num, line_str in enumerate(lines, start=1):
            if cmake_exec_re.search(line_str):
                accum = [line_str]
                idx = line_num - 1
                curr_idx = idx
                while ")" not in "".join(accum) and curr_idx + 1 < len(lines):
                    curr_idx += 1
                    accum.append(lines[curr_idx])
                    if len(accum) > max_lines or sum(len(s) for s in accum) > max_chars:
                        findings.append(
                            Finding(
                                norm_path,
                                line_num,
                                "HOST001",
                                "critical",
                                f"CMake execution command exceeds analyzable limit ({max_lines} lines / {max_chars} chars); fail-closed.",
                            )
                        )
                        break
                joined = " ".join(s.strip() for s in accum)
                commands.append((line_num, joined))

    return commands, findings


def strip_cpp_comments_and_strings(source: str) -> str:
    """Replace comments and string literals with spaces, preserving line breaks and character offsets."""
    chars = list(source)
    n = len(chars)
    i = 0
    while i < n:
        if i + 1 < n and chars[i] == "/" and chars[i + 1] == "/":
            chars[i] = " "
            chars[i + 1] = " "
            i += 2
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
        elif i + 1 < n and chars[i] == "/" and chars[i + 1] == "*":
            chars[i] = " "
            chars[i + 1] = " "
            i += 2
            while i < n and not (chars[i] == "*" and chars[i + 1] == "/"):
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < n and chars[i] == "*" and chars[i + 1] == "/":
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
        elif chars[i] == '"':
            chars[i] = " "
            i += 1
            while i < n and chars[i] != '"':
                if chars[i] == "\\":
                    chars[i] = " "
                    if i + 1 < n:
                        chars[i + 1] = " "
                        i += 2
                    else:
                        i += 1
                elif chars[i] == "\n":
                    i += 1
                else:
                    chars[i] = " "
                    i += 1
            if i < n and chars[i] == '"':
                chars[i] = " "
                i += 1
            elif chars[i] == "'":
                chars[i] = " "
                i += 1
                while i < n and chars[i] != "'":
                    if chars[i] == "\\":
                        chars[i] = " "
                        if i + 1 < n:
                            chars[i + 1] = " "
                            i += 2
                        else:
                            i += 1
                    elif chars[i] == "\n":
                        i += 1
                    else:
                        chars[i] = " "
                        i += 1
                if i < n and chars[i] == "'":
                    chars[i] = " "
                    i += 1
        elif chars[i] == "'":
            chars[i] = " "
            i += 1
            while i < n and chars[i] != "'":
                if chars[i] == "\\":
                    chars[i] = " "
                    if i + 1 < n:
                        chars[i + 1] = " "
                        i += 2
                    else:
                        i += 1
                elif chars[i] == "\n":
                    i += 1
                else:
                    chars[i] = " "
                    i += 1
            if i < n and chars[i] == "'":
                chars[i] = " "
                i += 1
        else:
            i += 1
    return "".join(chars)


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

    # 1. Native dangerous APIs
    sanitized_cpp = strip_cpp_comments(source)
    for rule, severity, pattern, message in HOST_NATIVE_API_RULES:
        for m in pattern.finditer(sanitized_cpp):
            line_no = source[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_no,
                    rule,
                    severity,
                    message,
                )
            )

    # 2. Process-launching sinks in C/C++ (system, _wsystem, ShellExecute, CreateProcess, popen, etc.)
    for m in CPP_PROCESS_SINK_RE.finditer(sanitized_cpp):
        line_no = source[: m.start()].count("\n") + 1
        sink_args = m.group(1)
        for rule, severity, pattern, message in HOST_CLI_MUTATION_RULES:
            if pattern.search(sink_args):
                findings.append(
                    Finding(
                        relative_path.as_posix(),
                        line_no,
                        rule,
                        severity,
                        message,
                    )
                )

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

    # Multiline scanning on sanitized code (with comments & strings masked)
    sanitized = strip_cpp_comments_and_strings(source)

    for m in CPP_KNOWN_VECTOR_RE.finditer(sanitized):
        line_no = source[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                relative_path.as_posix(),
                line_no,
                "CPP006",
                "critical",
                "Known-vector specialization or test ID branching is forbidden in kernel/C++ code.",
            )
        )

    for m in CPP_FINGERPRINT_MATCH_RE.finditer(sanitized):
        line_no = source[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                relative_path.as_posix(),
                line_no,
                "CPP006",
                "critical",
                "Input fingerprint specialization is forbidden in kernel/C++ code.",
            )
        )

    for m in CPP_EXPECTED_OUTPUT_COPY_RE.finditer(sanitized):
        line_no = source[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                relative_path.as_posix(),
                line_no,
                "CPP007",
                "critical",
                "Embedding or copying expected test outputs is forbidden.",
            )
        )

    for m in CPP_HOST_FALLBACK_CALL_RE.finditer(sanitized):
        line_no = source[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                relative_path.as_posix(),
                line_no,
                "CPP008",
                "critical",
                "Direct host/CPU fallback calls in kernel code are forbidden.",
            )
        )

    if CPP_CATCH_FALLBACK_RE.search(sanitized):
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

    lang = "powershell" if relative_path.suffix.lower() == ".ps1" else "shell"
    cmds, overflow_findings = assemble_logical_commands(relative_path, source, lang)
    findings.extend(overflow_findings)
    for line_num, cmd in cmds:
        for rule, severity, pattern, message in HOST_CLI_MUTATION_RULES:
            if pattern.search(cmd):
                findings.append(
                    Finding(
                        relative_path.as_posix(),
                        line_num,
                        rule,
                        severity,
                        message,
                    )
                )

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

    cmds, overflow_findings = assemble_logical_commands(relative_path, source, "cmake")
    findings.extend(overflow_findings)
    for line_num, cmd in cmds:
        for rule, severity, pattern, message in HOST_CLI_MUTATION_RULES:
            if pattern.search(cmd):
                findings.append(
                    Finding(
                        relative_path.as_posix(),
                        line_num,
                        rule,
                        severity,
                        message,
                    )
                )

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

    if relative_path.suffix.lower() in {".yaml", ".yml"}:
        cmds, overflow_findings = assemble_logical_commands(
            relative_path, source, "yaml"
        )
        findings.extend(overflow_findings)
        for line_num, cmd in cmds:
            for rule, severity, pattern, message in HOST_CLI_MUTATION_RULES:
                if pattern.search(cmd):
                    findings.append(
                        Finding(
                            relative_path.as_posix(),
                            line_num,
                            rule,
                            severity,
                            message,
                        )
                    )

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


PHYSICAL_CLAIM_RE = re.compile(
    r"(?i)\[VERIFIED PHYSICAL SILICON\]|"
    r"\bphysically verified\b|"
    r"\bexecuted on silicon\b|"
    r"\bverified on (?:phoenix\s+)?(?:aie2\s+)?hardware\b|"
    r"\bconfirmed on silicon\b|"
    r"\bpassed on (?:the\s+)?(?:physical\s+)?npu\b"
)


def is_claim_line(lines: list[str], idx: int) -> bool:
    line = lines[idx]
    if not DOC_STRONG_CLAIM_RE.search(line):
        return False

    line_lower = line.lower()

    if re.search(
        r"(?:physically verified|verified)\s*(?:gates|cases|suites)?\s*:\s*0\b",
        line_lower,
    ) or re.search(
        r"\b0\s+(?:[a-zA-Z_-]+\s+)*(?:physically\s+verified|verified|passed)\b",
        line_lower,
    ):
        return False
    if re.search(
        r"\bprohibited\s+(?:unqualified\s+)?phrases\b", line_lower
    ) or re.search(r"\bforbidden\s+phrases\b", line_lower):
        return False

    stripped = line.strip()
    if any(
        stripped.startswith(prefix)
        for prefix in ("- Use ", "- Inspect ", "- Enforce ", "- Prohibit ", "- [ ] ")
    ):
        return False
    if re.match(
        r"^\d+\.\s+Implementation\s+is\s+constant-time\b", stripped
    ) or re.match(r"^\d+\.\s+The\s+implementation\s+is\s+constant-time\b", stripped):
        return False

    phys_matches = list(PHYSICAL_CLAIM_RE.finditer(line))
    if phys_matches:
        for m in phys_matches:
            start = m.start()
            prev_bound = max(
                line_lower.rfind(";", 0, start),
                line_lower.rfind(".", 0, start),
                line_lower.rfind("|", 0, start),
            )
            clause_start = prev_bound + 1 if prev_bound != -1 else 0
            candidate_ends = [
                pos
                for pos in [
                    line_lower.find(";", m.end()),
                    line_lower.find(".", m.end()),
                    line_lower.find("|", m.end()),
                    len(line_lower),
                ]
                if pos != -1
            ]
            clause_end = min(candidate_ends) if candidate_ends else len(line_lower)
            clause = line_lower[clause_start:clause_end]
            has_neg = bool(
                re.search(
                    r"\b(?:not|never|no|without|un|non-|(?:is|are|was|were|being)\s+not|does\s+not\s+(?:claim|prove|demonstrate)|not\s+claimed|pending\s+physical\s+dispatch\s+corroboration|operator-retained|operator-supplied|historical\s+report|historical\s+document|legacy\s+pre-refactor|pre-refactor\s+self-reported)\b",
                    clause,
                )
            )
            if not has_neg:
                return True
        return False

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
        "treat skipped",
        "where the claim depends",
        "statements are not equivalent",
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
        "do not infer",
        "not claimed",
        "are not claimed",
        "is not claimed",
        "does not inherit",
        "operator-retained assertion",
        "operator-supplied",
        "unqualified phrases",
        "prohibited unqualified",
        "legacy pre-refactor",
        "historical report",
        "historical document",
        "pre-refactor self-reported",
    )
    return not any(d in line_lower for d in disclaimers)


def validate_markdown_accounting_tables(
    relative_path: Path, lines: list[str]
) -> list[Finding]:
    findings: list[Finding] = []
    norm_path = relative_path.as_posix()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if (
            line.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", lines[i + 1].strip())
        ):
            header_line_idx = i
            raw_header_cells = [
                c.strip() for c in lines[i].strip().strip("|").split("|")
            ]
            header_cells = [c.lower() for c in raw_header_cells]
            num_cols = len(header_cells)

            row_idx = i + 2
            table_rows: list[tuple[int, list[str]]] = []
            while row_idx < len(lines) and lines[row_idx].strip().startswith("|"):
                row_cells = [
                    c.strip() for c in lines[row_idx].strip().strip("|").split("|")
                ]
                table_rows.append((row_idx + 1, row_cells))
                row_idx += 1

            has_gate_col = any(
                any(k in h for k in ("gate", "milestone", "deliverable"))
                for h in header_cells
            )
            has_execution_outcome_col = any(
                any(
                    k in h
                    for k in (
                        "selected",
                        "executed",
                        "matching",
                        "failing",
                        "passed",
                        "failed",
                        "blocked",
                    )
                )
                for h in header_cells
            )

            if (has_gate_col or has_execution_outcome_col) and table_rows:
                # Row width validation
                for l_num, cells in table_rows:
                    if len(cells) != num_cols:
                        findings.append(
                            Finding(
                                norm_path,
                                l_num,
                                "DOC004",
                                "critical",
                                f"Inconsistent table row width: expected {num_cols} columns, got {len(cells)}.",
                            )
                        )

                gate_col_idx: int | None = None
                numeric_col_indices: dict[str, int] = {}
                for c_idx, h in enumerate(header_cells):
                    if (
                        any(k in h for k in ("gate", "milestone", "deliverable"))
                        and gate_col_idx is None
                    ):
                        gate_col_idx = c_idx
                    for k in (
                        "selected",
                        "executed",
                        "matching",
                        "failing",
                        "passed",
                        "failed",
                        "blocked",
                    ):
                        if k in h and k not in numeric_col_indices:
                            numeric_col_indices[k] = c_idx

                if numeric_col_indices:
                    (
                        canonical_gate_map,
                        canonical_gate_order,
                        extension_gate_map,
                    ) = get_canonical_gate_metadata()
                    detail_rows: list[tuple[int, list[str]]] = []
                    total_rows: list[tuple[int, list[str]]] = []
                    gate_ids_seen: set[str] = set()
                    gate_sequence: list[str] = []

                    context_before = " ".join(
                        lines[max(0, header_line_idx - 5) : header_line_idx]
                    ).lower()
                    claims_canonical_coverage = any(
                        term in context_before
                        for term in (
                            "canonical",
                            "master physical silicon",
                            "master silicon",
                            "complete suite",
                            "entire suite",
                            "repo-wide",
                            "suite accounting",
                            "all canonical",
                            "19 canonical",
                        )
                    )

                    for l_num, cells in table_rows:
                        clean_cells = [re.sub(r"[*`]", "", c).strip() for c in cells]
                        first_cell = clean_cells[0].lower() if clean_cells else ""
                        is_total_row = any(
                            t in first_cell
                            for t in ("total", "cumulative", "summary", "aggregate")
                        ) or any("total" in c.lower() for c in clean_cells)

                        if is_total_row:
                            total_rows.append((l_num, clean_cells))
                        else:
                            detail_rows.append((l_num, clean_cells))
                            if gate_col_idx is not None and gate_col_idx < len(
                                clean_cells
                            ):
                                g_raw = clean_cells[gate_col_idx]
                                g_match = re.search(
                                    r"\b(DR[0-9]+[a-zA-Z]?|GATE\s*\d+)\b",
                                    g_raw,
                                    re.IGNORECASE,
                                )
                                if g_match:
                                    norm_gid = g_match.group(1).upper().replace(" ", "")
                                    gate_sequence.append(norm_gid)
                                    if norm_gid in gate_ids_seen:
                                        findings.append(
                                            Finding(
                                                norm_path,
                                                l_num,
                                                "DOC005",
                                                "critical",
                                                f"Duplicate gate identifier '{norm_gid}' in accounting table.",
                                            )
                                        )
                                    gate_ids_seen.add(norm_gid)

                                    if claims_canonical_coverage:
                                        if (
                                            norm_gid not in canonical_gate_map
                                            and norm_gid not in extension_gate_map
                                        ):
                                            findings.append(
                                                Finding(
                                                    norm_path,
                                                    l_num,
                                                    "DOC005",
                                                    "critical",
                                                    f"Unknown or fabricated gate identifier '{norm_gid}' in accounting table.",
                                                )
                                            )
                                    else:
                                        dr_num_match = re.match(r"^DR(\d+)", norm_gid)
                                        if dr_num_match:
                                            dr_num = int(dr_num_match.group(1))
                                            if dr_num > 30:
                                                findings.append(
                                                    Finding(
                                                        norm_path,
                                                        l_num,
                                                        "DOC005",
                                                        "critical",
                                                        f"Unknown or fabricated gate identifier '{norm_gid}' in accounting table.",
                                                    )
                                                )

                    if claims_canonical_coverage:
                        if not total_rows:
                            findings.append(
                                Finding(
                                    norm_path,
                                    header_line_idx + 1,
                                    "DOC005",
                                    "critical",
                                    "Missing required Total row in canonical accounting table.",
                                )
                            )
                        for expected_gid in canonical_gate_order:
                            if expected_gid not in gate_ids_seen:
                                findings.append(
                                    Finding(
                                        norm_path,
                                        header_line_idx + 1,
                                        "DOC005",
                                        "critical",
                                        f"Missing canonical gate '{expected_gid}' in canonical accounting table.",
                                    )
                                )
                        filtered_canonical_seq = [
                            g for g in gate_sequence if g in canonical_gate_map
                        ]
                        expected_prefix = canonical_gate_order[
                            : len(filtered_canonical_seq)
                        ]
                        if filtered_canonical_seq != expected_prefix:
                            findings.append(
                                Finding(
                                    norm_path,
                                    header_line_idx + 1,
                                    "DOC005",
                                    "critical",
                                    f"Canonical gate rows are out of order: expected {expected_prefix}, found {filtered_canonical_seq}.",
                                )
                            )

                    # Validate numeric cells and row partition invariants
                    for l_num, cells in detail_rows + total_rows:
                        row_counts: dict[str, int] = {}
                        for col_name, col_idx in numeric_col_indices.items():
                            if col_idx < len(cells):
                                val_str = cells[col_idx]
                                if not re.match(r"^-?\d+$", val_str):
                                    findings.append(
                                        Finding(
                                            norm_path,
                                            l_num,
                                            "DOC004",
                                            "critical",
                                            f"Malformed numeric cell '{val_str}' in column '{col_name}'.",
                                        )
                                    )
                                else:
                                    val = int(val_str)
                                    if val < 0:
                                        findings.append(
                                            Finding(
                                                norm_path,
                                                l_num,
                                                "DOC004",
                                                "critical",
                                                f"Negative count '{val}' in accounting table column '{col_name}'.",
                                            )
                                        )
                                    row_counts[col_name] = val

                        sel = row_counts.get("selected")
                        exec_cnt = row_counts.get("executed")
                        match_cnt = row_counts.get("matching")
                        fail_cnt = row_counts.get("failing") or row_counts.get("failed")
                        pass_cnt = row_counts.get("passed")
                        blk_cnt = row_counts.get("blocked", 0)

                        if sel is not None and exec_cnt is not None and sel < exec_cnt:
                            findings.append(
                                Finding(
                                    norm_path,
                                    l_num,
                                    "DOC004",
                                    "critical",
                                    f"Row partition violation: cases_executed ({exec_cnt}) > cases_selected ({sel}).",
                                )
                            )

                        if (
                            exec_cnt is not None
                            and match_cnt is not None
                            and fail_cnt is not None
                            and match_cnt + fail_cnt + blk_cnt != exec_cnt
                        ):
                            findings.append(
                                Finding(
                                    norm_path,
                                    l_num,
                                    "DOC004",
                                    "critical",
                                    f"Row partition mismatch: matching ({match_cnt}) + failing ({fail_cnt}) != executed ({exec_cnt}).",
                                )
                            )

                        if (
                            exec_cnt is not None
                            and pass_cnt is not None
                            and fail_cnt is not None
                            and match_cnt is None
                            and pass_cnt + fail_cnt + blk_cnt != exec_cnt
                        ):
                            findings.append(
                                Finding(
                                    norm_path,
                                    l_num,
                                    "DOC004",
                                    "critical",
                                    f"Row partition mismatch: passed ({pass_cnt}) + failed ({fail_cnt}) != executed ({exec_cnt}).",
                                )
                            )

                    if len(total_rows) > 1:
                        first_tot_cells = total_rows[0][1]
                        for l_num, tot_cells in total_rows[1:]:
                            if tot_cells != first_tot_cells:
                                findings.append(
                                    Finding(
                                        norm_path,
                                        l_num,
                                        "DOC005",
                                        "critical",
                                        "Conflicting total rows detected in accounting table.",
                                    )
                                )

                    for col_name, col_idx in numeric_col_indices.items():
                        col_sum = 0
                        valid_count = 0
                        for l_num, cells in detail_rows:
                            if col_idx < len(cells):
                                val_str = cells[col_idx]
                                if re.match(r"^-?\d+$", val_str):
                                    val = int(val_str)
                                    if val >= 0:
                                        col_sum += val
                                        valid_count += 1

                        if total_rows and valid_count > 0:
                            for l_num, cells in total_rows:
                                if col_idx < len(cells):
                                    tot_str = cells[col_idx]
                                    if re.match(r"^-?\d+$", tot_str):
                                        tot_val = int(tot_str)
                                        if tot_val != col_sum:
                                            findings.append(
                                                Finding(
                                                    norm_path,
                                                    l_num,
                                                    "DOC004",
                                                    "critical",
                                                    f"Accounting table sum mismatch for column '{col_name}': detail rows sum to {col_sum} but Total row claims {tot_val}.",
                                                )
                                            )
            i = row_idx
        else:
            i += 1

    return findings


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
        if DOC_PROHIBITED_TERMINOLOGY_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "DOC006",
                    "critical",
                    "Prohibited terminology or uncorroborated claim regarding hidden inputs, scanner semantic proof, or cache freshness.",
                )
            )
        if DOC_REPO_ROOT_CITATION_RE.search(line):
            findings.append(
                Finding(
                    relative_path.as_posix(),
                    line_number,
                    "DOC007",
                    "critical",
                    "Repository root citation is insufficient; cite specific issue, PR, or commit permalink.",
                )
            )

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

    findings.extend(validate_markdown_accounting_tables(relative_path, lines))
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
    if suffix in {".ps1", ".sh", ".bat", ".cmd"}:
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
