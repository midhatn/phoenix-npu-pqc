# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR43: NIST SP 800-90B Continuous Hardware Health & Repetition/Adaptive Tests ABI
-----------------------------------------------------------------------------------------
NIST SP 800-90B Section 4.4 online health monitor state and alarm descriptors.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import enum
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

MAGIC_DESC_DR43 = b"\x01\x43\x39\x30"  # DR43 Descriptor Magic ('\x01C90')
MAGIC_RESULT_DR43 = b"90B4"              # DR43 Result Magic

RCT_CUTOFF_DEFAULT = 4      # Cutoff for 8-bit symbols with min-entropy >= 7.0
APT_WINDOW_SIZE = 512       # Standard sliding window
APT_CUTOFF_DEFAULT = 16     # Binomial cutoff for W=512, alpha=2^-20

class HealthStateEnum(enum.IntEnum):
    HEALTHY = 1
    RCT_ALARM_TRIPPED = 2
    APT_ALARM_TRIPPED = 3
    LOCKED_FAIL_CLOSED = 4

@dataclass
class RctState:
    current_symbol: Optional[int] = None
    repetition_count: int = 0
    max_observed_repetitions: int = 0
    alarm_tripped: bool = False

@dataclass
class AptState:
    window_size: int = APT_WINDOW_SIZE
    current_window_samples: int = 0
    target_symbol: Optional[int] = None
    target_count: int = 0
    max_observed_count: int = 0
    alarm_tripped: bool = False

@dataclass
class ContinuousHealthReport:
    is_healthy: bool
    total_samples_evaluated: int
    rct_alarm: bool
    apt_alarm: bool
    rct_max_repetition: int
    apt_max_frequency: int
    status_message: str = ""
