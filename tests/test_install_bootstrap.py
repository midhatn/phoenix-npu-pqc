"""Offline host-only regression tests for the extensionless bootstrap."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Self
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL = REPO_ROOT / "install"
LOADER = SourceFileLoader("pqc_install_bootstrap", str(INSTALL))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
BOOTSTRAP = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(BOOTSTRAP)


def completed(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0)


class FakeDownload:
    """Minimal context-managed response used to prove tests never use a network."""

    def __init__(self, content: bytes) -> None:
        self.stream = io.BytesIO(content)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.stream.close()

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


class InstallBootstrapTests(unittest.TestCase):
    def test_satisfied_dependency_verifies_then_hands_off_without_pip(self) -> None:
        commands: list[tuple[str, ...]] = []

        def fake_run(
            command: tuple[str, ...], **_: object
        ) -> subprocess.CompletedProcess[str]:
            commands.append(tuple(command))
            return completed(tuple(command))

        with (
            patch.object(BOOTSTRAP, "installed_numpy_version", return_value="2.5.2"),
            patch.object(BOOTSTRAP, "require_supported_interpreter"),
            patch.object(BOOTSTRAP.shutil, "which", return_value=None),
            patch.object(BOOTSTRAP.subprocess, "run", side_effect=fake_run),
        ):
            self.assertEqual(BOOTSTRAP.main([]), 0)

        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][:2], (sys.executable, "-c"))
        self.assertEqual(
            commands[1],
            (sys.executable, str(REPO_ROOT / "run_all_silicon_tests.py")),
        )
        self.assertFalse(any("pip" in command for command in commands))

    def test_missing_dependency_downloads_verified_wheel_then_hands_off(
        self,
    ) -> None:
        commands: list[tuple[str, ...]] = []
        payload = b"offline NumPy wheel fixture"
        digest = hashlib.sha256(payload).hexdigest()

        def fake_run(
            command: tuple[str, ...], **_: object
        ) -> subprocess.CompletedProcess[str]:
            commands.append(tuple(command))
            return completed(tuple(command))

        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "numpy-2.5.2-cp313-cp313-win_amd64.whl"
            with (
                patch.object(
                    BOOTSTRAP,
                    "installed_numpy_version",
                    side_effect=(None, "2.5.2"),
                ),
                patch.object(BOOTSTRAP, "require_supported_interpreter"),
                patch.object(BOOTSTRAP.shutil, "which", return_value=None),
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_CACHE", wheel),
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_BYTES", len(payload)),
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_SHA256", digest),
                patch.object(
                    BOOTSTRAP,
                    "urlopen",
                    return_value=FakeDownload(payload),
                ) as urlopen,
                patch.object(BOOTSTRAP.subprocess, "run", side_effect=fake_run),
            ):
                self.assertEqual(BOOTSTRAP.main([]), 0)
            urlopen.assert_called_once()

        self.assertEqual(
            commands[0],
            (
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(wheel),
            ),
        )
        self.assertEqual(commands[1][:2], (sys.executable, "-c"))
        self.assertEqual(
            commands[2],
            (sys.executable, str(REPO_ROOT / "run_all_silicon_tests.py")),
        )
        self.assertTrue(all(command[0] == sys.executable for command in commands))
        self.assertNotIn(BOOTSTRAP.NUMPY_WHEEL_URL, commands[0])

    def test_check_only_refuses_missing_dependency_without_subprocess(self) -> None:
        with (
            patch.object(BOOTSTRAP, "installed_numpy_version", return_value=None),
            patch.object(BOOTSTRAP, "require_supported_interpreter"),
            patch.object(BOOTSTRAP.shutil, "which", return_value=None),
            patch.object(BOOTSTRAP.subprocess, "run") as run,
        ):
            self.assertEqual(BOOTSTRAP.main(["--check-only"]), 1)
        run.assert_not_called()

    def test_valid_cached_wheel_never_calls_network(self) -> None:
        payload = b"verified cached wheel"
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / BOOTSTRAP.NUMPY_WHEEL_NAME
            wheel.write_bytes(payload)
            with (
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_CACHE", wheel),
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_BYTES", len(payload)),
                patch.object(
                    BOOTSTRAP,
                    "NUMPY_WHEEL_SHA256",
                    hashlib.sha256(payload).hexdigest(),
                ),
                patch.object(BOOTSTRAP, "urlopen") as urlopen,
            ):
                self.assertEqual(BOOTSTRAP.obtain_numpy_wheel(), wheel)
            urlopen.assert_not_called()

    def test_invalid_download_fails_integrity_check_without_pip(self) -> None:
        payload = b"tampered wheel"
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / BOOTSTRAP.NUMPY_WHEEL_NAME
            with (
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_CACHE", wheel),
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_BYTES", len(payload)),
                patch.object(BOOTSTRAP, "NUMPY_WHEEL_SHA256", "0" * 64),
                patch.object(BOOTSTRAP, "urlopen", return_value=FakeDownload(payload)),
                self.assertRaisesRegex(
                    BOOTSTRAP.BootstrapError, "integrity verification"
                ),
            ):
                BOOTSTRAP.obtain_numpy_wheel()
        self.assertFalse(wheel.exists())

    def test_supported_interpreter_guard_is_explicit_about_the_pinned_abi(self) -> None:
        with self.assertRaisesRegex(
            BOOTSTRAP.BootstrapError, "CPython 3.13 x64 on Windows"
        ):
            BOOTSTRAP.require_supported_interpreter(
                implementation="cpython",
                version=(3, 12),
                system="Windows",
                machine="AMD64",
            )

    def test_self_test_uses_only_the_host_safe_runner_dry_run(self) -> None:
        with patch.object(
            BOOTSTRAP.subprocess,
            "run",
            return_value=completed((sys.executable, "unused")),
        ) as run:
            self.assertEqual(BOOTSTRAP.main(["--self-test"]), 0)

        run.assert_called_once_with(
            (sys.executable, str(REPO_ROOT / "run_all_silicon_tests.py"), "--dry-run"),
            cwd=REPO_ROOT,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
