# SPDX-License-Identifier: Apache-2.0
"""Legacy runner retirement and migration stub.

This script has been retired to eliminate unverified PASS banners and enforce the
canonical evidence boundary. Execution is delegated to the authoritative runner at
the repository root: `run_all_silicon_tests.py`.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITATIVE_RUNNER = REPO_ROOT / "run_all_silicon_tests.py"


def main():
    print("=" * 80)
    print("NOTICE: tests/pqc_device_resident/run_all_silicon_tests.py has been retired.")
    print(f"Delegating execution to authoritative runner: {AUTHORITATIVE_RUNNER}")
    print("=" * 80)
    cmd = [sys.executable, str(AUTHORITATIVE_RUNNER)] + sys.argv[1:]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

