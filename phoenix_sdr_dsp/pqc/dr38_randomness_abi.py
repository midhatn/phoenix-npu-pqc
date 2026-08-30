# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR38: NIST SP 800-22 & BSI AIS 31 Statistical Randomness Battery ABI
-----------------------------------------------------------------------------
Standard packet descriptors and dataclasses for randomness and entropy testing.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

MAGIC_DESC_DR38 = b"\x01\x38\x53\x54"  # DR38 Descriptor Magic ('\x018ST')
MAGIC_RESULT_DR38 = b"ST38"              # DR38 Result Magic

@dataclass
class NistTestResult:
    test_name: str
    p_value: float
    passed: bool
    statistic: float
    details: str = ""

@dataclass
class BsiAis31TestResult:
    test_name: str
    passed: bool
    statistic: float
    threshold_range: Tuple[float, float]
    details: str = ""

@dataclass
class RandomnessBatteryReport:
    sample_bytes_evaluated: int
    nist_results: List[NistTestResult] = field(default_factory=list)
    bsi_results: List[BsiAis31TestResult] = field(default_factory=list)
    shannon_entropy: float = 8.0
    all_passed: bool = True
