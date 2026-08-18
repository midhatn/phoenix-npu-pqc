"""Host-only tests for the native Windows installer and its launcher.

Everything here is mocked or offline. No network request is made, no XRT SDK or
mlir-aie tree is fetched, no ``iron_setup`` runs, no AIE program is compiled, and
no NPU is opened. The tests assert the installer's integrity and fail-closed
behaviour plus the launcher's handoff contract to the canonical physical runner
``run_all_silicon_tests.py``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Self
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
INSTALL_LAUNCHER = REPO / "install"
INSTALL_IMPLEMENTATION = REPO / "install.py"
TOOLCHAIN = REPO / "toolchain.yaml"


def _load(path: Path, name: str):
    """Import a module from an explicit path, including the extensionless one."""
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # Register before execution so @dataclass can resolve the defining module.
    sys.modules[name] = module
    loader.exec_module(module)
    return module


installer = _load(INSTALL_IMPLEMENTATION, "phoenix_native_installer")
launcher = _load(INSTALL_LAUNCHER, "phoenix_install_launcher")


class FakeResponse(io.RawIOBase):
    """Minimal urlopen stand-in returning fixed bytes."""

    def __init__(self, content: bytes) -> None:
        self._buffer = io.BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


class LauncherHandoffTests(unittest.TestCase):
    def test_default_install_appends_the_physical_runner_handoff(self) -> None:
        self.assertEqual(launcher.build_install_argv([]), ["--run-tests"])
        self.assertEqual(
            launcher.build_install_argv(["--force"]), ["--force", "--run-tests"]
        )

    def test_maintenance_modes_never_request_dispatch(self) -> None:
        for option in sorted(launcher.MAINTENANCE_OPTIONS):
            self.assertEqual(launcher.build_install_argv([option]), [option])

    def test_explicit_opt_out_removes_the_handoff(self) -> None:
        self.assertEqual(launcher.build_install_argv(["--no-tests"]), [])
        self.assertEqual(
            launcher.build_install_argv(["--no-tests", "--force"]), ["--force"]
        )

    def test_conflicting_dispatch_flags_fail_closed_in_either_order(self) -> None:
        for argv in (
            ["--no-tests", "--run-tests"],
            ["--run-tests", "--no-tests"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError):
                    launcher.build_install_argv(argv)
                with (
                    patch.object(launcher.runpy, "run_path") as dispatched,
                    patch("sys.stderr", io.StringIO()) as stderr,
                ):
                    self.assertEqual(launcher.main(argv), 2)
                dispatched.assert_not_called()
                self.assertIn("mutually exclusive", stderr.getvalue())

    def test_conflicting_dispatch_flags_exit_two_without_handoff_in_subprocess(
        self,
    ) -> None:
        """The extensionless executable must return main's fail-closed status."""

        launcher_source = INSTALL_LAUNCHER.read_text(encoding="utf-8")
        for argv in (
            ["--no-tests", "--run-tests"],
            ["--run-tests", "--no-tests"],
        ):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                launcher_path = root / "install"
                implementation = root / "install.py"
                handoff_marker = root / "install-handoff.txt"
                launcher_path.write_text(launcher_source, encoding="utf-8")
                implementation.write_text(
                    "from pathlib import Path\n"
                    f"Path({str(handoff_marker)!r}).write_text('handoff', "
                    "encoding='utf-8')\n",
                    encoding="utf-8",
                )

                completed = subprocess.run(
                    [sys.executable, str(launcher_path), *argv],
                    capture_output=True,
                    check=False,
                    cwd=root,
                    text=True,
                )

                self.assertEqual(completed.returncode, 2)
                self.assertIn("mutually exclusive", completed.stderr)
                self.assertFalse(handoff_marker.exists())

    def test_launcher_targets_the_maintained_implementation(self) -> None:
        self.assertEqual(launcher.INSTALL_IMPLEMENTATION, "install.py")
        self.assertEqual(launcher.CANONICAL_PHYSICAL_RUNNER, "run_all_silicon_tests.py")
        self.assertTrue(INSTALL_IMPLEMENTATION.is_file())


class InstallerPinTests(unittest.TestCase):
    def test_pins_are_read_from_toolchain_yaml_not_hardcoded(self) -> None:
        pins = installer.load_pins(REPO)
        text = TOOLCHAIN.read_text(encoding="utf-8")
        self.assertIn(pins.xrt_sha256, text)
        self.assertIn(str(pins.xrt_bytes), text)
        self.assertEqual(pins.xrt_archive_release, "2.21.75")
        self.assertEqual(pins.xrt_runtime_version, "2.21.0")
        self.assertIn(
            f"/download/{pins.xrt_archive_release}/",
            pins.xrt_url,
        )
        self.assertIn(pins.mlir_commit, text)
        self.assertIn(pins.mlir_wheel_sha256, text)
        self.assertIn(str(pins.mlir_wheel_bytes), text)
        self.assertEqual(len(pins.xrt_sha256), 64)
        self.assertEqual(len(pins.mlir_wheel_sha256), 64)
        self.assertEqual(len(pins.mlir_commit), 40)
        self.assertEqual(pins.python_required, (3, 13))

    def test_xrt_metadata_rejects_an_archive_release_url_mismatch(self) -> None:
        source = TOOLCHAIN.read_text(encoding="utf-8")
        mismatched = source.replace(
            'release_url: "https://github.com/Xilinx/XRT/releases/tag/2.21.75"',
            'release_url: "https://github.com/Xilinx/XRT/releases/tag/9.9.9"',
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "toolchain.yaml").write_text(mismatched, encoding="utf-8")
            with self.assertRaises(installer.BootstrapError):
                installer.load_pins(root)

    def test_canonical_runner_is_the_only_post_install_handoff(self) -> None:
        self.assertEqual(
            installer.CANONICAL_PHYSICAL_RUNNER, "run_all_silicon_tests.py"
        )
        self.assertEqual(installer.HOST_PREFLIGHT_RUNNER, "run_all_pqc_tests.py")


class DownloadIntegrityTests(unittest.TestCase):
    def test_verified_download_is_written_once_and_reused_offline(self) -> None:
        payload = b"phoenix-native-installer-download-test\n"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "cache" / "artifact.bin"
            with patch.object(
                installer, "urlopen", return_value=FakeResponse(payload)
            ) as opened:
                installer.download_file(
                    "https://example.invalid/artifact.bin",
                    destination,
                    len(payload),
                    digest,
                )
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(destination.read_bytes(), payload)

            # A second call must be satisfied from the verified cache.
            with patch.object(installer, "urlopen") as reopened:
                installer.download_file(
                    "https://example.invalid/artifact.bin",
                    destination,
                    len(payload),
                    digest,
                )
            reopened.assert_not_called()

    def test_size_or_hash_mismatch_fails_closed(self) -> None:
        payload = b"tampered-artifact\n"
        wrong_digest = hashlib.sha256(b"expected-artifact\n").hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "artifact.bin"
            with (
                patch.object(installer, "urlopen", return_value=FakeResponse(payload)),
                self.assertRaises(installer.BootstrapError),
            ):
                installer.download_file(
                    "https://example.invalid/artifact.bin",
                    destination,
                    len(payload),
                    wrong_digest,
                )

            destination_two = Path(tmp) / "artifact2.bin"
            with (
                patch.object(installer, "urlopen", return_value=FakeResponse(payload)),
                self.assertRaises(installer.BootstrapError),
            ):
                installer.download_file(
                    "https://example.invalid/artifact.bin",
                    destination_two,
                    len(payload) + 1,
                    hashlib.sha256(payload).hexdigest(),
                )


class ExtractedArchiveIntegrityTests(unittest.TestCase):
    def test_tampered_extracted_member_is_replaced_not_accepted_by_marker(self) -> None:
        payload = b"verified pyxrt binding\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "xrt.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("xrt_sdk/xrt/python/pyxrt.pyd", payload)
            archive_bytes = archive.stat().st_size
            archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
            destination = root / "xrt_windows_sdk"
            required = destination / "xrt_sdk" / "xrt" / "python" / "pyxrt.pyd"

            self.assertEqual(
                installer.ensure_extracted_zip(
                    archive,
                    destination,
                    ".phoenix-xrt-sha256",
                    archive_bytes,
                    archive_sha256,
                    required,
                ),
                "extracted",
            )
            # The marker is writable diagnostic metadata and must not decide
            # whether a mutated cached binary is accepted.
            (destination / ".phoenix-xrt-sha256").write_text(
                archive_sha256 + "\n", encoding="utf-8"
            )
            required.write_bytes(b"tampered binding")
            self.assertEqual(
                installer.ensure_extracted_zip(
                    archive,
                    destination,
                    ".phoenix-xrt-sha256",
                    archive_bytes,
                    archive_sha256,
                    required,
                ),
                "repaired",
            )
            self.assertEqual(required.read_bytes(), payload)

    def test_tampered_cached_archive_fails_before_extracted_cache_reuse(self) -> None:
        payload = b"verified pyxrt binding\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "xrt.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("xrt_sdk/xrt/python/pyxrt.pyd", payload)
            archive_bytes = archive.stat().st_size
            archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
            destination = root / "xrt_windows_sdk"
            required = destination / "xrt_sdk" / "xrt" / "python" / "pyxrt.pyd"
            installer.ensure_extracted_zip(
                archive,
                destination,
                ".phoenix-xrt-sha256",
                archive_bytes,
                archive_sha256,
                required,
            )
            tampered_archive = bytearray(archive.read_bytes())
            tampered_archive[-1] ^= 0x01
            archive.write_bytes(tampered_archive)
            self.assertEqual(archive.stat().st_size, archive_bytes)
            with self.assertRaises(installer.BootstrapError):
                installer.ensure_extracted_zip(
                    archive,
                    destination,
                    ".phoenix-xrt-sha256",
                    archive_bytes,
                    archive_sha256,
                    required,
                )


class MaintenanceModeTests(unittest.TestCase):
    def test_self_test_is_offline_and_never_dispatches(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            self.assertEqual(installer.self_test(), 0)
        text = buffer.getvalue()
        # The self-test exercises download/repair/hash-failure logic against a
        # local file:// URL only. It never reaches the network or the NPU.
        self.assertIn("file:///", text)
        self.assertNotIn("https://", text)
        for forbidden in ("iron_setup", "clang++", "Backend:", "TOTAL "):
            self.assertNotIn(forbidden, text)

    def test_argument_parser_exposes_only_non_dispatching_maintenance_modes(
        self,
    ) -> None:
        for option in ("--check-only", "--download-only", "--self-test"):
            parsed = installer.parse_args([option])
            self.assertFalse(parsed.run_tests, msg=option)
        self.assertTrue(installer.parse_args(["--run-tests"]).run_tests)
        self.assertFalse(installer.parse_args([]).run_tests)

    def test_integrity_disclosure_states_what_is_not_hash_locked(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            installer.print_integrity_disclosure()
        text = buffer.getvalue()
        self.assertIn("NOT hash-locked", text)
        self.assertIn("iron_setup", text)
        self.assertIn("wheelhouse", text)
        self.assertIn("does not claim", text)
        self.assertIn("optional host/reference", text)
        self.assertIn("not installed by this physical installer", text)

    def test_default_installer_has_no_unhashed_reference_package_install(self) -> None:
        source = INSTALL_IMPLEMENTATION.read_text(encoding="utf-8")
        for package in ("kyber-py==", "dilithium-py==", "pytest=="):
            self.assertNotIn(package, source)
        self.assertIn("not installed by this physical installer", source)


if __name__ == "__main__":
    unittest.main()
