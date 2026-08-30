# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR39: dudect Microarchitectural Constant-Time Side-Channel Leakage Verifier ABI
----------------------------------------------------------------------------------------
TVLA trace distributions, Welford statistical state, and Welch's t-test dataclasses.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

MAGIC_DESC_DR39 = b"\x01\x39\x44\x55"  # DR39 Descriptor Magic ('\x019DU')
MAGIC_RESULT_DR39 = b"DU39"              # DR39 Result Magic

DUDECT_T_THRESHOLD = 4.5  # Standard threshold: |t| < 4.5 indicates p > 0.001 (constant time)

@dataclass
class DudectDistribution:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, x: float):
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def variance(self) -> float:
        if self.count < 2:
            return 0.0
        return self.m2 / (self.count - 1)

@dataclass
class DudectWelchResult:
    primitive_name: str
    t_statistic: float
    is_constant_time: bool
    samples_class0: int
    samples_class1: int
    mean0: float
    mean1: float
    details: str = ""

@dataclass
class SideChannelLeakageReport:
    total_primitives_evaluated: int
    passed_primitives: int
    all_constant_time: bool
    results: List[DudectWelchResult] = field(default_factory=list)
