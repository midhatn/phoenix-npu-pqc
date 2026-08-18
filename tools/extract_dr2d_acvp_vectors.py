"""Offline extraction and verification for the pinned DR2d ACVP corpus.

This utility never contacts a network service.  Given local ACVP
``prompt.json`` and ``expectedResults.json`` files from the pinned commit, it
checks their supplied SHA-256 digests and either writes the compact DR2d
corpus or verifies that an existing compact corpus maps exactly to tcId 1..25.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

COMMIT = "975de31eb83d87039ec88934fdc47d8c312b892d"
SOURCE = (
    "https://github.com/usnistgov/ACVP-Server/tree/"
    f"{COMMIT}/gen-val/json-files/ML-KEM-keyGen-FIPS203"
)
PROMPT_SHA256 = "3f9ce34f6c836c77958bad2729e837c3b213f44ac36c3065976e7acca6389523"
EXPECTED_SHA256 = "a253d0ad91c95ebea5b409673defef0aa49d65d4ed72286399e2e798ddf073a4"
TC_IDS = tuple(range(1, 26))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(path: Path, expected: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(
            f"{path.name} SHA-256 mismatch: expected {expected}, got {actual}"
        )


def _groups(document: dict[str, Any]) -> list[dict[str, Any]]:
    groups = document.get("testGroups")
    if not isinstance(groups, list):
        raise TypeError("ACVP source lacks a testGroups list")
    return groups


def _mlkem512_group(document: dict[str, Any]) -> dict[str, Any]:
    groups = [
        group
        for group in _groups(document)
        if group.get("parameterSet") == "ML-KEM-512"
    ]
    if len(groups) != 1:
        raise ValueError(f"expected exactly one ML-KEM-512 group, got {len(groups)}")
    return groups[0]


def _tests_by_id(group: dict[str, Any]) -> dict[int, dict[str, Any]]:
    tests = group.get("tests")
    if not isinstance(tests, list):
        raise TypeError("ACVP group lacks tests")
    return {item["tcId"]: item for item in tests if type(item.get("tcId")) is int}


def _expected_keys(item: dict[str, Any]) -> tuple[str, str]:
    result = item.get("expectedResults", item)
    if not isinstance(result, dict):
        raise TypeError("expected result record is not an object")
    ek, dk = result.get("ek"), result.get("dk")
    if not isinstance(ek, str) or not isinstance(dk, str):
        raise TypeError("expected result lacks hexadecimal ek/dk")
    return ek.upper(), dk.upper()


def extract(prompt_path: Path, expected_path: Path) -> dict[str, Any]:
    """Verify local source hashes and return the pinned compact DR2d corpus."""
    _require_hash(prompt_path, PROMPT_SHA256)
    _require_hash(expected_path, EXPECTED_SHA256)
    prompt_group = _mlkem512_group(json.loads(prompt_path.read_text(encoding="utf-8")))
    expected_document = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_group = next(
        (
            group
            for group in _groups(expected_document)
            if group.get("tgId") == prompt_group.get("tgId")
        ),
        None,
    )
    if expected_group is None:
        expected_group = _mlkem512_group(expected_document)
    prompt_tests, expected_tests = (
        _tests_by_id(prompt_group),
        _tests_by_id(expected_group),
    )
    if not all(tc_id in prompt_tests and tc_id in expected_tests for tc_id in TC_IDS):
        raise ValueError("ML-KEM-512 source does not contain every tcId 1..25")
    tests = []
    for tc_id in TC_IDS:
        d = prompt_tests[tc_id].get("d")
        if not isinstance(d, str) or len(bytes.fromhex(d)) != 32:
            raise ValueError(f"tcId {tc_id} has no valid d[32]")
        ek, dk = _expected_keys(expected_tests[tc_id])
        if len(bytes.fromhex(ek)) != 800 or len(bytes.fromhex(dk)) < 768:
            raise ValueError(f"tcId {tc_id} has invalid ML-KEM-512 key lengths")
        tests.append(
            {"tcId": tc_id, "d": d.upper(), "ekPKE": ek, "dkPKE": dk[: 2 * 768]}
        )
    return {
        "source": SOURCE,
        "sourceCommit": COMMIT,
        "sourceFiles": ["prompt.json", "expectedResults.json"],
        "sourceSha256": {
            "prompt.json": PROMPT_SHA256,
            "expectedResults.json": EXPECTED_SHA256,
        },
        "extraction": "ML-KEM-512 tcId 1..25; ekPKE=expected ek; dkPKE=first 768 bytes of expected dk",
        "algorithm": "ML-KEM",
        "mode": "keyGen",
        "revision": "FIPS203",
        "parameterSet": "ML-KEM-512",
        "derivation": "ekPKE is ACVP ek; dkPKE is the first 768 bytes of ACVP dk",
        "tests": tests,
    }


def _verify_compact(compact_path: Path) -> dict[str, Any]:
    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    expected_metadata = {
        "source": SOURCE,
        "sourceCommit": COMMIT,
        "sourceFiles": ["prompt.json", "expectedResults.json"],
        "sourceSha256": {
            "prompt.json": PROMPT_SHA256,
            "expectedResults.json": EXPECTED_SHA256,
        },
    }
    for key, value in expected_metadata.items():
        if compact.get(key) != value:
            raise ValueError(f"compact corpus {key} does not match pinned provenance")
    tests = compact.get("tests")
    if not isinstance(tests, list) or [item.get("tcId") for item in tests] != list(
        TC_IDS
    ):
        raise ValueError("compact corpus does not contain ordered tcId 1..25")
    for item in tests:
        if (
            len(bytes.fromhex(item.get("d", ""))) != 32
            or len(bytes.fromhex(item.get("ekPKE", ""))) != 800
            or len(bytes.fromhex(item.get("dkPKE", ""))) != 768
        ):
            raise ValueError(
                f"compact corpus tcId {item.get('tcId')} has invalid lengths"
            )
    return compact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--expected-results", type=Path)
    parser.add_argument("--compact", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if (args.prompt is None) != (args.expected_results is None):
        parser.error("--prompt and --expected-results must be supplied together")
    if args.prompt is None:
        _verify_compact(args.compact)
        print(f"verified compact DR2d corpus: {args.compact}")
        return 0
    extracted = extract(args.prompt, args.expected_results)
    if args.write:
        args.compact.write_text(
            json.dumps(extracted, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote compact DR2d corpus: {args.compact}")
    else:
        current = _verify_compact(args.compact)
        if current["tests"] != extracted["tests"]:
            raise ValueError(
                "compact corpus tests mapping does not match verified ACVP sources"
            )
        print(f"verified source-to-compact mapping: {args.compact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
