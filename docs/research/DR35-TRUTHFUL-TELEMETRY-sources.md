# DR35 Research and Provenance: Physical Power, Energy & Truthful Hardware Telemetry

## Milestone Deliverable Context
- Deliverable: **DR35 (Truthful Physical Power, Energy & Hardware Telemetry Harvester on AMD Phoenix AIE2)**
- Standards: AMD XRT Telemetry Specification, Windows PnP / CM Device APIs, ACPI / RAPL Energy Counters
- Target Hardware: AMD Phoenix NPU (AIE2 / XDNA1, PCI Device ID 1502)
- Classification & Integrity Rules:
  - Classification: **[HOST RUNTIME] / [HOST TOOLING]**.
  - Strict adherence to `AGENTS.md` and `zero-speculation-policy.md`.
  - Anti-Fabrication Invariant: Telemetry metrics must derive exclusively from verified hardware APIs (XRT `get_info`, Windows PnP `CM_Get_DevNode_Status`, high-resolution perf counters).
  - Never fabricate fake sensor readings, mock milliwatts, or hardcoded temperatures. When a hardware rail is unmonitored by vendor firmware, report `SENSOR_UNAVAILABLE` or `UNSUPPORTED_ON_HOST` with explicit status codes.

## Citation Ledger

### Citation 1: AMD XRT Device Management & Telemetry API
- Source Title: XRT Native C++ / Python API Reference Guide: Device Telemetry & Sensors
- Author / Organization: Advanced Micro Devices (AMD) / Xilinx
- Source Type: Vendor documentation
- Full URL: https://xilinx.github.io/XRT/master/html/
- Publication Date: 2024-02-15
- Access Date: 2026-09-05T15:02:00Z
- Relevant Section: Section "Device Information & Telemetry" (`pyxrt.device.get_info`, `pyxrt.xrt_info_device`)
- Exact Technical Claim:
  - Queries physical device name, BDF (Bus/Device/Function), driver version, and hardware operational state directly from the kernel driver.
  - On integrated laptop APUs (e.g. Phoenix 7040/8040 series), certain desktop/datacenter telemetry registers (e.g. discrete 12V rail ammeters) are not exposed by the silicon firmware.
  - Software must gracefully distinguish available hardware properties (BDF, device name, DMA status, execution latency) from absent BMC metrics without emitting mock values.
- How Claim Was Independently Verified: Verified via live `pyxrt.device(0)` inspection on physical Phoenix APU hardware.
- Affected Files: `phoenix_sdr_dsp/pqc/dr35_telemetry_harvester.py`, `tests/test_pqc_dr35_contract.py`.
- Confidence Level: PRIMARY

### Citation 2: Microsoft Windows SetupAPI & PnP Device Management API
- Source Title: Device Information Sets and Device Installation Properties in Windows
- Author / Organization: Microsoft Corporation
- Source Type: Official documentation
- Full URL: https://learn.microsoft.com/en-us/windows/win32/devinst/device-information-sets
- Publication Date: 2023-11-28
- Access Date: 2026-09-05T15:02:00Z
- Relevant Section: PnP Device Node Status (`CM_Get_DevNode_Status`, `Get-PnpDevice` properties)
- Exact Technical Claim:
  - Reports hardware PnP device operational status (`ConfigManagerErrorCode == 0`, Problem Code 0, Status `OK`).
  - Queries hardware device IDs (`PCI\VEN_1022&DEV_1502...`), power state `D0` (fully active), and driver package metadata (`amdnpu.inf`).
- How Claim Was Independently Verified: Corroborated with Windows PowerShell `Get-PnpDevice -FriendlyName "*NPU*"` and setupapi registry queries.
- Affected Files: `phoenix_sdr_dsp/pqc/dr35_telemetry_harvester.py`.
- Confidence Level: PRIMARY

### Citation 3: Repository Anti-Fabrication & Telemetry Policy
- Source Title: Agent Directive: Hardware Ground Truth and Zero-Fabrication Engineering
- Source Type: Repository policy (`AGENTS.md` & `zero-speculation-policy.md`)
- Relevant Section: Ground truth & Hardware behavior
- Exact Technical Claim:
  - "Never catch a hardware failure and return a host, reference, simulated, cached, repaired, or precomputed result."
  - "Placeholder kernels, identity transforms, no-op providers, decorative descriptors, fixed outputs, and hardcoded success totals are forbidden."
  - "Telemetry claims must use real hardware counters and never invent mock or decorative sensors."
- How Claim Was Independently Verified: Enforced via policy scanner `tools/agent_integrity.py` and strict schema validation.
- Affected Files: `phoenix_sdr_dsp/pqc/dr35_telemetry_harvester.py`.
- Confidence Level: PRIMARY
