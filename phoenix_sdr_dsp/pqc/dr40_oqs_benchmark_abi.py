# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR40: Open Quantum Safe (liboqs / PQClean) Cross-Validation & eBACS Benchmark ABI
-----------------------------------------------------------------------------------------
Standard packet descriptors, golden vector dataclasses, and eBACS benchmark metrics.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import struct
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

MAGIC_DESC_DR40 = b"\x01\x40\x4F\x51"  # DR40 Descriptor Magic ('\x01@OQ')
MAGIC_RESULT_DR40 = b"OQ40"              # DR40 Result Magic

@dataclass
class OqsVectorEntry:
    scheme_name: str
    seed: bytes
    message: bytes = b""
    expected_pk: Optional[bytes] = None
    expected_ct: Optional[bytes] = None
    expected_ss: Optional[bytes] = None

@dataclass
class OqsValidationVerdict:
    scheme_name: str
    operation: str
    matched: bool
    details: str = ""

@dataclass
class EbacsBenchmarkMetric:
    scheme_name: str
    operation: str
    cycles_per_op: float
    ops_per_sec: float
    latency_us: float
    stack_bytes_used: int

@dataclass
class OqsBenchmarkSuiteReport:
    total_tests: int
    passed_tests: int
    all_matched: bool
    validation_results: List[OqsValidationVerdict] = field(default_factory=list)
    benchmark_metrics: List[EbacsBenchmarkMetric] = field(default_factory=list)
