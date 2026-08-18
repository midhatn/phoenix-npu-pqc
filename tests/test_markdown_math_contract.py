"""Host-only regression checks for maintained GitHub Markdown math."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROTECTED_EVIDENCE = REPO / "docs" / "pqc_dr2_evidence_20260818"
THIRD_PARTY = REPO / "third_party"


def maintained_markdown() -> tuple[Path, ...]:
    """Return project Markdown, excluding immutable evidence and dependencies."""
    return tuple(
        path
        for path in sorted(REPO.rglob("*.md"))
        if PROTECTED_EVIDENCE not in path.parents
        and THIRD_PARTY not in path.parents
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
    )


def prose_without_inline_code(line: str) -> str:
    """Remove simple inline-code spans before inspecting Markdown delimiters."""
    return "".join(line.split("`")[::2])


def unescaped_count(text: str, delimiter: str) -> int:
    """Count an exact LaTex delimiter that is not itself escaped."""
    return len(re.findall(rf"(?<!\\){re.escape(delimiter)}", text))


class MarkdownMathContractTests(unittest.TestCase):
    def test_third_party_markdown_is_not_treated_as_maintained(self) -> None:
        self.assertTrue(
            all(THIRD_PARTY not in path.parents for path in maintained_markdown())
        )

    def test_maintained_markdown_uses_no_operatorname(self) -> None:
        offenders = [
            path.relative_to(REPO)
            for path in maintained_markdown()
            if r"\operatorname" in path.read_text(encoding="utf-8-sig")
        ]
        self.assertEqual(offenders, [])

    def test_maintained_math_delimiters_are_balanced(self) -> None:
        problems: list[str] = []
        for path in maintained_markdown():
            in_fence = False
            dollar_display_open = False
            bracket_display_open = False
            parenthesis_depth = 0
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8-sig").splitlines(), start=1
            ):
                if line.lstrip().startswith(("```", "~~~")):
                    in_fence = not in_fence
                    continue
                if in_fence or line.startswith(("    ", "\t")):
                    continue

                prose = prose_without_inline_code(line)
                if prose.strip() == "$$":
                    dollar_display_open = not dollar_display_open
                    continue
                if dollar_display_open:
                    continue

                dollars = re.findall(r"(?<!\\)\$", prose)
                if len(dollars) % 2:
                    problems.append(f"{path.relative_to(REPO)}:{line_number}")
                bracket_display_open ^= bool(unescaped_count(prose, r"\[") % 2)
                bracket_display_open ^= bool(unescaped_count(prose, r"\]") % 2)
                parenthesis_depth += unescaped_count(prose, r"\(")
                parenthesis_depth -= unescaped_count(prose, r"\)")
                if parenthesis_depth < 0:
                    problems.append(f"{path.relative_to(REPO)}:{line_number}")
                    parenthesis_depth = 0
            if dollar_display_open:
                problems.append(f"{path.relative_to(REPO)}:unclosed $$ display")
            if bracket_display_open:
                problems.append(f"{path.relative_to(REPO)}:unclosed \\[ display")
            if parenthesis_depth:
                problems.append(f"{path.relative_to(REPO)}:unbalanced \\( inline math")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
