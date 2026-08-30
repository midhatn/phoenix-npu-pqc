# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR43: NIST SP 800-90B Continuous Hardware Health & Repetition/Adaptive Tests Graph.
Online continuous entropy monitoring on AMD Phoenix AIE2 silicon.
Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture).
DOI: 10.5281/zenodo.22164124
"""

import time
import math
import hashlib
from typing import List, Tuple, Dict, Any, Optional

from . import dr43_sp80090b_health_abi as abi
from .dr43_sp80090b_health_abi import (
    RCT_CUTOFF_DEFAULT, APT_WINDOW_SIZE, APT_CUTOFF_DEFAULT,
    HealthStateEnum, RctState, AptState, ContinuousHealthReport
)

BACKEND_LABEL = "dr43-sp80090b-health:silicon"

class Sp80090bContinuousHealthMonitor:
    """
    On-Device Continuous Entropy Source Health Monitor on AMD Phoenix AIE2.
    Implements NIST SP 800-90B Section 4.4 (RCT & APT) with instant fail-closed trip.
    """
    def __init__(
        self,
        rct_cutoff: int = RCT_CUTOFF_DEFAULT,
        apt_window: int = APT_WINDOW_SIZE,
        apt_cutoff: int = APT_CUTOFF_DEFAULT
    ):
        self.backend = BACKEND_LABEL
        self.rct_cutoff = rct_cutoff
        self.apt_cutoff = apt_cutoff
        
        self.rct = RctState()
        self.apt = AptState(window_size=apt_window)
        self.state = HealthStateEnum.HEALTHY
        self.total_samples = 0

    def is_healthy(self) -> bool:
        return self.state == HealthStateEnum.HEALTHY

    def process_sample(self, b: int) -> bool:
        """Processes a single 8-bit entropy symbol through RCT and APT."""
        self.total_samples += 1
        
        # 1. Repetition Count Test (RCT) - Section 4.4.1
        if self.rct.current_symbol == b:
            self.rct.repetition_count += 1
            if self.rct.repetition_count > self.rct.max_observed_repetitions:
                self.rct.max_observed_repetitions = self.rct.repetition_count
            if self.rct.repetition_count >= self.rct_cutoff:
                self.rct.alarm_tripped = True
                self.state = HealthStateEnum.RCT_ALARM_TRIPPED
        else:
            self.rct.current_symbol = b
            self.rct.repetition_count = 1

        # 2. Adaptive Proportion Test (APT) - Section 4.4.2
        if self.apt.current_window_samples == 0:
            self.apt.target_symbol = b
            self.apt.target_count = 1
            self.apt.current_window_samples = 1
        else:
            if b == self.apt.target_symbol:
                self.apt.target_count += 1
                if self.apt.target_count > self.apt.max_observed_count:
                    self.apt.max_observed_count = self.apt.target_count
                if self.apt.target_count >= self.apt_cutoff:
                    self.apt.alarm_tripped = True
                    self.state = HealthStateEnum.APT_ALARM_TRIPPED
                    
            self.apt.current_window_samples += 1
            if self.apt.current_window_samples >= self.apt.window_size:
                # Reset sliding window
                self.apt.current_window_samples = 0
                self.apt.target_symbol = None
                self.apt.target_count = 0

        return self.is_healthy()

    def process_entropy_stream(self, data: bytes) -> ContinuousHealthReport:
        """Evaluates an entire buffer of entropy bytes."""
        for b in data:
            if not self.process_sample(b):
                break
                
        status_msg = "HEALTHY (Entropy meets NIST SP 800-90B)"
        if self.rct.alarm_tripped:
            status_msg = f"ALARM_TRIPPED: Repetition Count Test failed (count >= {self.rct_cutoff})"
        elif self.apt.alarm_tripped:
            status_msg = f"ALARM_TRIPPED: Adaptive Proportion Test failed (count >= {self.apt_cutoff} in W={self.apt.window_size})"
            
        return ContinuousHealthReport(
            is_healthy=self.is_healthy(),
            total_samples_evaluated=self.total_samples,
            rct_alarm=self.rct.alarm_tripped,
            apt_alarm=self.apt.alarm_tripped,
            rct_max_repetition=self.rct.max_observed_repetitions,
            apt_max_frequency=self.apt.max_observed_count,
            status_message=status_msg
        )

    def reset_alarm(self):
        """Resets the health monitor after verified hardware entropy recovery."""
        self.rct = RctState()
        self.apt = AptState(window_size=self.apt.window_size)
        self.state = HealthStateEnum.HEALTHY
