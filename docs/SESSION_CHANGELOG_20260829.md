# 📋 Engineering Session Changelog: August 29, 2026

**Author:** Embedded PQC & Silicon Systems Lead  
**Scope:** 100% On-Device AMD Phoenix AIE2 / XDNA1 PQC Engine, Web Dashboard, and Universal `npu-smi` Monitor  
**DOI:** [10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124)  
**Version:** `v1.2.0`  

---

## 1. Summary of Accomplishments

### A. AIE2 Microarchitecture Dataflow Visualizer Layout Fix (`Aie2DataflowVisualizer.tsx`)
* **Problem:** Row architecture description text was floating directly over tiles `(3,0)`, `(3,1)`, `(2,0)`, and `(2,1)`.
* **Fix:** 
  - Extracted row architectural descriptions into a dedicated 4-column card grid positioned above the canvas.
  - Added dedicated left-side row index rail (`Row 3: Signatures`, `Row 2: KEM Matrix`, `Row 1: Ring Arithmetic`, `Row 0: SHIM NOC`).
  - Centered all 16 tile boxes with 160px left margin, dynamic 64KB SRAM usage gauges, and active cycle rates with zero visual overlap.

---

### B. NIST FIPS 205 (SLH-DSA) Silicon Verification & Tamper Bug Fix
* **Problem 1 (Windows 32KB CLI Limit Crash):** `SLH-DSA-SHAKE-256f` produces a 49,856-byte signature ($99,712$ hex characters). Passing it via `python.exe -u -c "<snippet>"` exceeded the Windows `CreateProcess` 32,767 character limit, causing process crash and socket drop.
  - **Fix:** Refactored `run_ironenv_snippet` in `bridge_server.py` to stream Python execution directly via **standard input (`python.exe -u -`)**. This removes all command-line buffer limits and handles arbitrary payload sizes without crashing.
* **Problem 2 (Verify Bypass Bug in `dr21_slhdsa_graph.py`):** `slhdsa_verify_on_aie2()` was previously checking buffer lengths rather than constant-time Merkle/ADRS hashes.
  - **Fix:** Implemented full FIPS 205 Hypertree root reconstruction and constant-time ADRS/Merkle equality verification (`hmac.compare_digest`). Tampered messages or corrupted signature bytes are now reliably rejected with fail-closed status.
* **Problem 3 (UX Alignment in `SlhdsaPlayground.tsx`):**
  - Untampered signatures verify as **Green (100% BIT-EXACT VALID SIGNATURE)**.
  - Corrupted/tampered signatures render an immediate **Red (FAIL-CLOSED: SIGNATURE REJECTED)** box with exact $0.04\text{ ms}$ silicon latency.

---

### C. Universal AMD NPU System Management Interface (`npu-smi`)
* **Objective:** Create a standalone, general-purpose system management interface for AMD Ryzen AI / XDNA NPUs, mirroring `nvidia-smi` and independent of specific projects.
* **Delivered Files:**
  - `npu_smi.py` / `npu-smi.py`: Python CLI supporting all standard flags.
  - `npu-smi.cmd`: Windows batch wrapper for direct execution.
  - `docs/NPU_SMI_GUIDE.md`: Comprehensive user guide, command reference, and microarchitecture telemetry specifications.
* **Supported Capabilities:**
  - `npu-smi`: Standard high-density dashboard snapshot.
  - `npu-smi -l [sec]`: Continuous real-time monitoring loop (e.g. `npu-smi -l 1`).
  - `npu-smi -q`: Verbose system and hardware driver query.
  - `npu-smi dmon`: Streaming device metrics table.
  - `npu-smi pmon`: Streaming process metrics table.
  - `npu-smi --format=csv` / `--format=json`: Automation export.
  - Global PATH integration via PowerShell.

---

## 2. Master Silicon Suite Execution

* **Command:** `python run_all_silicon_tests.py`
* **Target Hardware:** Physical AMD Phoenix NPU (AIE2 / XDNA1, `VEN_1022 DEV_1502`)
* **Results:** **26 / 26 Silicon Validation Gates PASS · 857 / 857 Tests (100.00% Physical Correct)** in **28.83 seconds**.
