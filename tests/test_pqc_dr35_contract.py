# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR35:
Physical Power, Energy & Truthful Hardware Telemetry Harvester on AMD Phoenix AIE2.
"""

import unittest
from datetime import datetime

from phoenix_sdr_dsp.pqc.dr35_telemetry_harvester import (
    SensorStatus,
    HardwareTelemetrySnapshot,
    harvest_hardware_telemetry,
    profile_execution,
    validate_telemetry_integrity,
)


class DR35TelemetryHarvesterContractTests(unittest.TestCase):

    def test_01_execution_boundary_label(self):
        """Validates truthful [HOST RUNTIME] execution boundary labeling."""
        snapshot = harvest_hardware_telemetry()
        self.assertEqual(snapshot.execution_label, "[HOST RUNTIME]")

    def test_02_harvest_hardware_telemetry_fields(self):
        """Validates telemetry snapshot structure and required fields."""
        snapshot = harvest_hardware_telemetry()
        self.assertTrue(snapshot.device_found)
        self.assertEqual(snapshot.driver_name, "amdnpu")
        self.assertIn("0066:00:01.1", snapshot.pci_bdf)
        self.assertEqual(snapshot.problem_code, 0)
        self.assertEqual(snapshot.power_state, "D0_ACTIVE")
        self.assertGreater(snapshot.sample_duration_ms, 0.0)

    def test_03_zero_fabrication_sensor_integrity(self):
        """Validates zero-fabrication policy: no mock numeric values for unmonitored sensors."""
        snapshot = harvest_hardware_telemetry()
        is_valid = validate_telemetry_integrity(snapshot)
        self.assertTrue(is_valid)

        if snapshot.power_sensor_status == SensorStatus.UNAVAILABLE_ON_INTEGRATED_APU:
            self.assertIsNone(snapshot.power_watts)

        if snapshot.temperature_sensor_status == SensorStatus.UNAVAILABLE_ON_INTEGRATED_APU:
            self.assertIsNone(snapshot.temperature_celsius)

    def test_04_profile_execution_wrapper(self):
        """Validates profiling wrapper capturing latency and pre/post telemetry."""
        def dummy_workload(n: int) -> int:
            return sum(i * i for i in range(n))

        res, snapshot = profile_execution(dummy_workload, 1000)
        self.assertEqual(res, sum(i * i for i in range(1000)))
        self.assertGreater(snapshot.sample_duration_ms, 0.0)
        self.assertTrue(validate_telemetry_integrity(snapshot))

    def test_05_rejection_of_fabricated_snapshot(self):
        """Validates that validate_telemetry_integrity rejects snapshots with mock sensor values."""
        # Fabricated power wattage on unmonitored APU rail
        fake_snapshot = HardwareTelemetrySnapshot(
            timestamp_iso=datetime.now().isoformat(),
            device_found=True,
            device_name="Phoenix AIE2",
            pci_bdf="0066:00:01.1",
            driver_name="amdnpu",
            pnp_status="OK",
            problem_code=0,
            power_state="D0_ACTIVE",
            power_sensor_status=SensorStatus.UNAVAILABLE_ON_INTEGRATED_APU,
            power_watts=18.5, # FORBIDDEN: Fake number on unavailable sensor
            temperature_sensor_status=SensorStatus.UNAVAILABLE_ON_INTEGRATED_APU,
            temperature_celsius=None,
            sample_duration_ms=1.2,
            execution_label="[HOST RUNTIME]",
        )
        self.assertFalse(validate_telemetry_integrity(fake_snapshot))

        # Incorrect execution label
        bad_label_snapshot = HardwareTelemetrySnapshot(
            timestamp_iso=datetime.now().isoformat(),
            device_found=True,
            device_name="Phoenix AIE2",
            pci_bdf="0066:00:01.1",
            driver_name="amdnpu",
            pnp_status="OK",
            problem_code=0,
            power_state="D0_ACTIVE",
            power_sensor_status=SensorStatus.UNAVAILABLE_ON_INTEGRATED_APU,
            power_watts=None,
            temperature_sensor_status=SensorStatus.UNAVAILABLE_ON_INTEGRATED_APU,
            temperature_celsius=None,
            sample_duration_ms=1.2,
            execution_label="[ON-TILE SILICON]", # FORBIDDEN: Harvester runs on host
        )
        self.assertFalse(validate_telemetry_integrity(bad_label_snapshot))


if __name__ == "__main__":
    unittest.main()
