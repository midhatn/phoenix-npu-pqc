"""Host-only regression tests for the stdlib installer pin parser."""

from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = runpy.run_path(REPO_ROOT / "install.py", run_name="install_pin_tests")
load_pins = INSTALLER["load_pins"]


class InstallerPinTests(unittest.TestCase):
    def test_load_pins_reads_nested_machine_readable_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "toolchain.yaml").write_text(
                """
host:
  python:
    min: "3.11"
    max_exclusive: "3.15"
drivers:
  amd_npu_driver:
    minimum: "99.1.2.3"
toolchain:
  mlir_aie:
    verified_commit: "0123456789abcdef"
    wheel_name: "mlir-test.whl"
    wheel_url: "https://example.invalid/mlir-test.whl"
    wheel_bytes: 123
    wheel_sha256: "abcdef"
  xrt:
    verified_version: "9.9.9"
    release_url: "https://example.invalid/releases/tag/9.9.9"
    sdk_url: "https://example.invalid/xrt.zip"
    sdk_bytes: 456
    sdk_sha256: "123456"
bootstrap:
  script: "install.py"
""".lstrip(),
                encoding="utf-8",
            )

            pins = load_pins(root)

        self.assertEqual(pins.xrt_url, "https://example.invalid/xrt.zip")
        self.assertEqual(pins.xrt_tag, "9.9.9")
        self.assertEqual(pins.xrt_bytes, 456)
        self.assertEqual(pins.xrt_sha256, "123456")
        self.assertEqual(pins.mlir_commit, "0123456789abcdef")
        self.assertEqual(pins.mlir_wheel_name, "mlir-test.whl")
        self.assertEqual(pins.mlir_wheel_url, "https://example.invalid/mlir-test.whl")
        self.assertEqual(pins.mlir_wheel_bytes, 123)
        self.assertEqual(pins.mlir_wheel_sha256, "abcdef")
        self.assertEqual(pins.npu_driver_min, "99.1.2.3")
        self.assertEqual(pins.python_min, (3, 11))
        self.assertEqual(pins.python_max_excl, (3, 15))


if __name__ == "__main__":
    unittest.main()
