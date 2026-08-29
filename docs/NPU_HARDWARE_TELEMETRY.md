# AMD Ryzen AI NPU: Real-Time Hardware Telemetry & Monitoring Guide

This guide documents how to query and monitor **100% genuine physical silicon telemetry** on the AMD Phoenix / Hawk Point APU (Ryzen 9 7940HS / 7840HS / 8845HS / 8945HS w/ AIE2 & XDNA1) using AMD's official driver tools.

---

## 1. ⚡ Live Silicon Telemetry Stream (100ms Continuous Polling)

To stream real-time hardware execution contexts, column allocations, memory residency, and packet submission/completion counters:

### Option A: Continuous Scrolling Stream (with `--verbose`)
```powershell
while ($true) { & "C:\Windows\System32\AMD\xrt-smi.exe" examine -r aie-partitions --verbose; Start-Sleep -Milliseconds 100 }
```
*(Press `Ctrl + C` anytime to stop)*

---

### Option B: Clean In-Place Screen Refresh (Live Monitor Mode)
```powershell
while ($true) { Clear-Host; & "C:\Windows\System32\AMD\xrt-smi.exe" examine -r aie-partitions --verbose; Start-Sleep -Milliseconds 100 }
```

---

## 2. 📊 Field-by-Field Silicon Metric Guide

When workloads execute on the NPU (e.g. running `python run_all_silicon_tests.py` in a separate terminal), the AMD XRT driver outputs:

```text
-----------------------------
[0066:00:01.1] : NPU Phoenix
-----------------------------
AIE Partitions
  Total Memory Usage: 128 MB
  Partition Index   : 0
    Columns: [1, 2, 3, 4]
    HW Contexts:
      |PID                 |Ctx ID     |Submissions |Migrations  |Err  |Priority |
      |Process Name        |Status     |Completions |Suspensions |     |GOPS     |
      |Memory Usage        |Instr BO   |            |            |     |FPS      |
      |                    |           |            |            |     |Latency  |
      |====================|===========|============|============|=====|=========|
      |32148               |57         |31422       |0           |0    |Normal   |
      |python.exe          |Active     |31422       |0           |     |N/A      |
      |128 MB              |64 KB      |            |            |     |N/A      |
      |--------------------|-----------|------------|------------|-----|---------|
AIE Columns
  |Column  |HW Context Slot  |
  |--------|-----------------|
  |1       |[57, 58]         |
  |2       |[57, 58]         |
  |3       |[57, 58]         |
  |4       |[57, 58]         |
```

| Field | Physical Silicon Reality |
| :--- | :--- |
| **`Columns: [1, 2, 3, 4]`** | Real physical allocation of all 4 AIE2 vector processing columns ($4 \times 4$ tile matrix). |
| **`Total Memory Usage: 128 MB`** | Contiguous physical host-resident DMA Buffer Object (BO) mapped to the NPU SHIM NOC. |
| **`Instr BO: 64 KB`** | Microcode instruction payload loaded into the AIE2 tile program memory. |
| **`PID` & `Ctx ID`** | Real active OS Process ID (`python.exe`) and hardware execution context slot ID (`Ctx 57, 58`). |
| **`Submissions / Completions`** | Exact real-time packet counters incremented by the silicon hardware execution ring buffer. |
| **`Err: 0`** | Hardware exception and fault register (zero indicates clean, bit-exact execution). |
| **`AIE Columns 1..4 -> [57, 58]`** | Dynamic hardware context binding across physical tile columns. |

---

## 3. 🧪 Silicon Diagnostics & Power Profile Management

```powershell
# Inspect static device properties, driver (32.0.20102.3930), and firmware (1.5.5.391):
& "C:\Windows\System32\AMD\xrt-smi.exe" examine

# Run official silicon latency & throughput validation:
& "C:\Windows\System32\AMD\xrt-smi.exe" validate --verbose

# Set hardware power profile mode:
& "C:\Windows\System32\AMD\xrt-smi.exe" configure --pmode [default|performance|turbo|balanced|powersaver]
```
