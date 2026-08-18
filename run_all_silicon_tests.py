#!/usr/bin/env python3
"""Compatibility entrypoint for the retired hardware-named test command.

Phoenix NPU PQC does not authorize or run hardware through this script. It
forwards only to the explicit host-safe suite in ``run_all_pqc_tests.py``.
Native-only physical gates are retained as evidence and are not invoked here.
"""

from run_all_pqc_tests import main

if __name__ == "__main__":
    raise SystemExit(main())
