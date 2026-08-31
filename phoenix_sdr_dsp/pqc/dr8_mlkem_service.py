# SPDX-License-Identifier: Apache-2.0
"""Unified DR8 ML-KEM service dispatcher on AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2).

Dispatches NIST FIPS 203 KeyGen, Encaps, and Decaps operations across all 3 parameter sets:
- ML-KEM-512  (k=2, eta1=3, eta2=2, du=10, dv=4)
- ML-KEM-768  (k=3, eta1=2, eta2=2, du=10, dv=4)
- ML-KEM-1024 (k=4, eta1=2, eta2=2, du=11, dv=5)
"""
import hashlib
import os
from pathlib import Path
from typing import Any, Tuple

from phoenix_sdr_dsp.pqc.dr5_mlkem512_keygen_graph import run_mlkem512_keygen as kg512
from phoenix_sdr_dsp.pqc.dr6_mlkem512_encaps_graph import run_mlkem512_encaps as enc512
from phoenix_sdr_dsp.pqc.dr7_mlkem512_decaps_graph import run_mlkem512_decaps as dec512
from phoenix_sdr_dsp.pqc.dr8_mlkem768_keygen_graph import run_mlkem768_keygen as kg768
from phoenix_sdr_dsp.pqc.dr8_mlkem768_encaps_graph import run_mlkem768_encaps as enc768
from phoenix_sdr_dsp.pqc.dr8_mlkem768_decaps_graph import run_mlkem768_decaps as dec768
from phoenix_sdr_dsp.pqc.dr8_mlkem1024_keygen_graph import run_mlkem1024_keygen as kg1024
from phoenix_sdr_dsp.pqc.dr8_mlkem1024_encaps_graph import run_mlkem1024_encaps as enc1024
from phoenix_sdr_dsp.pqc.dr8_mlkem1024_decaps_graph import run_mlkem1024_decaps as dec1024

BACKEND_LABEL = "dr8-mlkem-unified:silicon"
KERNEL_REL_PATH = "phoenix_sdr_dsp/pqc/kernels/dr8_mlkem768_keygen_finalize.cc"


class NativeBackendUnavailable(RuntimeError):
    """The native IRON/XRT DR8 backend is unavailable or failed closed."""


def check_emulation_and_redirection_excluded() -> None:
    """Fail closed if XCL_EMULATION_MODE or XRT_INI_PATH runtime redirection variables are set."""
    emulation_mode = os.environ.get("XCL_EMULATION_MODE")
    if emulation_mode and emulation_mode.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XCL_EMULATION_MODE={emulation_mode!r} is set. "
            "Hardware ground truth forbids simulation or emulation backends."
        )
    xrt_ini = os.environ.get("XRT_INI_PATH")
    if xrt_ini and xrt_ini.strip():
        raise NativeBackendUnavailable(
            f"Physical silicon execution rejected: XRT_INI_PATH={xrt_ini!r} is set. "
            "Hardware ground truth forbids custom runtime configuration redirection."
        )


def require_hardware_runtime() -> None:
    """Check hardware runtime availability and fail closed if unavailable."""
    check_emulation_and_redirection_excluded()
    try:
        import pyxrt
        dev = pyxrt.device(0)
    except Exception as exc:
        raise NativeBackendUnavailable("DR8 physical silicon requires XRT device(0)") from exc


def get_kernel_artifact_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Return verified path and SHA-256 digest of the DR8 AIE2 kernel source."""
    root = repo_root or Path(__file__).resolve().parents[2]
    kernel_path = root / KERNEL_REL_PATH
    if not kernel_path.is_file():
        raise FileNotFoundError(f"Kernel source file not found: {kernel_path}")
    data = kernel_path.read_bytes()
    return {
        "path": KERNEL_REL_PATH,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest().lower(),
    }

def mlkem_keygen(d: bytes, z: bytes, param_set: str = "ML-KEM-768", req_id: int = 1) -> Tuple[bytes, bytes]:
    """Execute NIST FIPS 203 ML-KEM.KeyGen 100% on-device on Phoenix NPU."""
    if param_set in ("ML-KEM-512", "512", 2):
        return kg512(d, z, req_id)
    elif param_set in ("ML-KEM-768", "768", 3):
        return kg768(d, z, req_id)
    elif param_set in ("ML-KEM-1024", "1024", 4):
        return kg1024(d, z, req_id)
    else:
        raise ValueError(f"Unsupported ML-KEM parameter set: {param_set}")

def mlkem_encaps(ek: bytes, m: bytes, param_set: str = "ML-KEM-768", req_id: int = 1) -> Tuple[bytes, bytes]:
    """Execute NIST FIPS 203 ML-KEM.Encaps 100% on-device on Phoenix NPU."""
    if param_set in ("ML-KEM-512", "512", 2):
        return enc512(ek, m, req_id)
    elif param_set in ("ML-KEM-768", "768", 3):
        return enc768(ek, m, req_id)
    elif param_set in ("ML-KEM-1024", "1024", 4):
        return enc1024(ek, m, req_id)
    else:
        raise ValueError(f"Unsupported ML-KEM parameter set: {param_set}")

def mlkem_decaps(dk: bytes, c: bytes, param_set: str = "ML-KEM-768", req_id: int = 1) -> bytes:
    """Execute NIST FIPS 203 ML-KEM.Decaps 100% on-device on Phoenix NPU."""
    if param_set in ("ML-KEM-512", "512", 2):
        return dec512(dk, c, req_id)
    elif param_set in ("ML-KEM-768", "768", 3):
        return dec768(dk, c, req_id)
    elif param_set in ("ML-KEM-1024", "1024", 4):
        return dec1024(dk, c, req_id)
    else:
        raise ValueError(f"Unsupported ML-KEM parameter set: {param_set}")
