"""AST guard for forbidden production imports of the repository test tree."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path


def _is_tests_module(value: str) -> bool:
    return value == "tests" or value.startswith("tests.")


class _TestDependencyVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[str] = []
        self.importlib_names = {"importlib"}
        self.import_module_names = {"import_module"}

    def _record(self, node: ast.AST, detail: str) -> None:
        self.findings.append(f"{self.filename}:{node.lineno}: {detail}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _is_tests_module(alias.name):
                self._record(node, f"import {alias.name}")
            if alias.name == "importlib":
                self.importlib_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and _is_tests_module(node.module):
            self._record(node, f"from {node.module} import ...")
        if node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    self.import_module_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not node.args or not isinstance(node.args[0], ast.Constant):
            self.generic_visit(node)
            return
        module = node.args[0].value
        if not isinstance(module, str) or not _is_tests_module(module):
            self.generic_visit(node)
            return

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.importlib_names
        ):
            self._record(node, f"dynamic import_module({module!r})")
        elif isinstance(node.func, ast.Name) and (
            node.func.id in self.import_module_names or node.func.id == "__import__"
        ):
            self._record(node, f"dynamic {node.func.id}({module!r})")
        self.generic_visit(node)


def find_test_dependency_imports(source: str, filename: str = "<source>") -> list[str]:
    """Return direct and supported dynamic imports of ``tests``/``tests.*``."""

    visitor = _TestDependencyVisitor(filename)
    visitor.visit(ast.parse(source, filename=filename))
    return visitor.findings


def assert_no_test_dependency_imports(paths: Iterable[Path]) -> None:
    """Raise with line-addressable findings for Python production source files."""

    findings: list[str] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        findings.extend(
            find_test_dependency_imports(
                path.read_text(encoding="utf-8"),
                str(path),
            )
        )
    if findings:
        joined = "\n".join(findings)
        raise AssertionError(f"production source imports test code:\n{joined}")
