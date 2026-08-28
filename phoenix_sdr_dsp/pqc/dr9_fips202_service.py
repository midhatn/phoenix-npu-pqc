# SPDX-License-Identifier: Apache-2.0
"""DR9 Reusable NIST FIPS 202 High-Level Service API."""
from typing import Optional
from .dr9_fips202_graph import run_fips202_service

class FIPS202NpuService:
    """Reusable FIPS 202 cryptographic service on AMD Phoenix NPU (XDNA1/AIE2)."""

    @staticmethod
    def sha3_224(msg: bytes) -> bytes:
        """Compute SHA3-224 digest on NPU."""
        return run_fips202_service("SHA3-224", msg, 28)

    @staticmethod
    def sha3_256(msg: bytes) -> bytes:
        """Compute SHA3-256 digest on NPU."""
        return run_fips202_service("SHA3-256", msg, 32)

    @staticmethod
    def sha3_384(msg: bytes) -> bytes:
        """Compute SHA3-384 digest on NPU."""
        return run_fips202_service("SHA3-384", msg, 48)

    @staticmethod
    def sha3_512(msg: bytes) -> bytes:
        """Compute SHA3-512 digest on NPU."""
        return run_fips202_service("SHA3-512", msg, 64)

    @staticmethod
    def shake128(msg: bytes, out_len: int = 32) -> bytes:
        """Compute SHAKE128 XOF output on NPU."""
        return run_fips202_service("SHAKE128", msg, out_len)

    @staticmethod
    def shake256(msg: bytes, out_len: int = 64) -> bytes:
        """Compute SHAKE256 XOF output on NPU."""
        return run_fips202_service("SHAKE256", msg, out_len)
