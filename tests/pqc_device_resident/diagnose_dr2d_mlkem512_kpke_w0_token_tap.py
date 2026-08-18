"""Explicitly gated native entrypoint for the diagnostic-only DR2d W0 token tap.

Do not set the authorization environment variable until a separate review has
approved one specific native call.  This script contains no reference algorithm.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from phoenix_sdr_dsp.pqc import (
    dr2d_mlkem512_kpke_keygen_w0_token_tap_graph as tap,
)

AUTHORIZATION_ENV = "PQC_DR2D_W0_TAP_NATIVE_AUTHORIZATION"
AUTHORIZATION_VALUE = "AUTHORIZED_AFTER_W0_TAP_COMPILE_ONLY_REVIEW"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one explicitly authorized W0 token-tap diagnostic call."
    )
    parser.add_argument(
        "--d-hex", required=True, help="exactly 32 bytes as 64 hex digits"
    )
    parser.add_argument("--request-id", required=True, type=lambda x: int(x, 0))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _main() -> int:
    args = _parse_args()
    if os.environ.get(AUTHORIZATION_ENV) != AUTHORIZATION_VALUE:
        print(
            "REFUSED: no post-compile-only W0 token-tap native authorization is present."
        )
        return 3
    try:
        d = bytes.fromhex(args.d_hex)
    except ValueError as exc:
        print(f"INPUT ERROR: invalid D hex ({exc})")
        return 2
    if len(d) != 32:
        print(f"INPUT ERROR: D must be exactly 32 bytes, got {len(d)}")
        return 2
    output = args.output.resolve()
    if output.exists():
        print(f"REFUSED: output already exists: {output}")
        return 3
    try:
        before = tap.verify_production_hashes()
        tap.require_hardware_runtime()
        print(f"Backend: {tap.BACKEND_LABEL}")
        token = tap.run_w0_token_tap(d, args.request_id)
        after = tap.verify_production_hashes()
        if after != before:
            raise tap.DiagnosticIntegrityError(
                "pinned production hashes changed during diagnostic"
            )
        with output.open("xb") as stream:
            stream.write(token)
        print(f"W0_TOKEN_BYTES={len(token)}")
        print(f"W0_TOKEN_SHA256={hashlib.sha256(token).hexdigest()}")
        for name, digest in tap.token_region_hashes(token).items():
            print(f"REGION_SHA256 {name}={digest}")
        print(f"OUTPUT={output}")
        print("DIAGNOSTIC ONLY: this is not a DR2d production pass.")
        return 0
    except Exception as exc:  # noqa: BLE001 - diagnostic failure is explicit
        print(f"W0 TOKEN TAP ERROR ({type(exc).__name__}: {exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
