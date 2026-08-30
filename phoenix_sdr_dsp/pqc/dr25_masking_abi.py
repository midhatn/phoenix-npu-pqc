# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR25: Higher-Order Masked Polynomial Arithmetic & On-Chip PRNG ABI
----------------------------------------------------------------------------
Side-channel defense (DPA/CPA) and fault injection countermeasure interface.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

MAGIC_DESC_DR25 = b"\x01\x25\x4D\x53"   # DR25 Descriptor Magic ('\x01%MS')
MAGIC_RESULT_DR25 = b"MS25"                # DR25 Result Magic

# Masking Order Constants
MASK_ORDER_1 = 1  # 2 shares (d=1, 1st-order probing secure)
MASK_ORDER_2 = 2  # 3 shares (d=2, 2nd-order probing secure)

# Standard Moduli Constants
MOD_MLKEM_Q3329   = 3329      # NIST FIPS 203 ML-KEM modulus
MOD_MLDSA_Q8380417 = 8380417   # NIST FIPS 204 ML-DSA modulus

# Polynomial Degree
N_DEGREE = 256

@dataclass
class MaskedPoly:
    """
    Represents an arithmetic masked polynomial in R_q = Z_q[X]/(X^256 + 1).
    Contains (order + 1) shares such that sum(shares) mod q == unmasked_poly.
    """
    order: int
    modulus: int
    shares: List[List[int]] # List of (order + 1) polynomials, each of length 256

    def unmask(self) -> List[int]:
        """Reconstruct unmasked polynomial coefficients in [0, modulus - 1]."""
        res = [0] * N_DEGREE
        for share in self.shares:
            for i in range(N_DEGREE):
                res[i] = (res[i] + share[i]) % self.modulus
        return res

    def to_bytes(self) -> bytes:
        """Serializes masked polynomial shares into binary buffer."""
        header = struct.pack(">IIII", self.order, self.modulus, len(self.shares), N_DEGREE)
        body = bytearray()
        for share in self.shares:
            if self.modulus <= 65535: # 16-bit encoding (ML-KEM q=3329)
                for coeff in share:
                    body.extend(struct.pack(">H", coeff % self.modulus))
            else:                     # 32-bit encoding (ML-DSA q=8380417)
                for coeff in share:
                    body.extend(struct.pack(">I", coeff % self.modulus))
        return header + bytes(body)

    @classmethod
    def from_bytes(cls, data: bytes) -> "MaskedPoly":
        """Deserializes masked polynomial shares from binary buffer."""
        order, modulus, num_shares, degree = struct.unpack(">IIII", data[:16])
        if degree != N_DEGREE:
            raise ValueError(f"Expected degree {N_DEGREE}, got {degree}")
        
        offset = 16
        shares = []
        for _ in range(num_shares):
            share = []
            if modulus <= 65535:
                for _ in range(N_DEGREE):
                    share.append(struct.unpack(">H", data[offset:offset + 2])[0])
                    offset += 2
            else:
                for _ in range(N_DEGREE):
                    share.append(struct.unpack(">I", data[offset:offset + 4])[0])
                    offset += 4
            shares.append(share)
        return cls(order, modulus, shares)
