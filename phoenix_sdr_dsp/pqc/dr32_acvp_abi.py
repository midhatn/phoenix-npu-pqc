# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR32: Automated NIST ACVP Server Test Vector Harness ABI
------------------------------------------------------------------
NIST SP 800-140Br1 / FIPS 140-3 CMVP Automated Cryptographic Validation Protocol ABI.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

MAGIC_DESC_DR32 = b"\x01\x32\x41\x43"   # DR32 Descriptor Magic ('\x012AC')
MAGIC_RESULT_DR32 = b"AC32"                # DR32 Result Magic

# NIST ACVP Algorithm Identifiers
ACVP_ALGO_MLKEM_512       = "ML-KEM-512"
ACVP_ALGO_MLKEM_768       = "ML-KEM-768"
ACVP_ALGO_MLKEM_1024      = "ML-KEM-1024"
ACVP_ALGO_MLDSA_44        = "ML-DSA-44"
ACVP_ALGO_MLDSA_65        = "ML-DSA-65"
ACVP_ALGO_MLDSA_87        = "ML-DSA-87"
ACVP_ALGO_SLHDSA_128S     = "SLH-DSA-SHAKE-128s"
ACVP_ALGO_LMS             = "LMS"

# Test Group Types
ACVP_TYPE_AFT = "AFT"  # Algorithm Functional Test
ACVP_TYPE_VAL = "VAL"  # Validation Test
ACVP_TYPE_KAT = "KAT"  # Known Answer Test

@dataclass
class AcvpTestCase:
    tcId: int
    inputs: Dict[str, Any]

@dataclass
class AcvpTestGroup:
    tgId: int
    algorithm: str
    mode: str          # "keyGen", "encaps", "decaps", "sigGen", "sigVer"
    testType: str      # "AFT", "VAL"
    tests: List[AcvpTestCase] = field(default_factory=list)

@dataclass
class AcvpResponseCase:
    tcId: int
    outputs: Dict[str, Any]
    testPassed: Optional[bool] = None

@dataclass
class AcvpResponseGroup:
    tgId: int
    tests: List[AcvpResponseCase] = field(default_factory=list)

@dataclass
class AcvpValidationReport:
    total_groups: int
    total_cases: int
    passed_cases: int
    failed_cases: int
    hardware_crc_verified: bool
    execution_time_ms: float
    boundary_verdict: str
