# Clean-Clone Release Readiness & Onboarding Validation Report

## 1. Executive Summary

This report documents the end-to-end fresh-clone onboarding and execution validation for the `phoenix-npu-pqc` repository, conducted in an isolated directory from the remote GitHub repository.

* **Validation Date**: 2026-09-05
* **Repository URL**: `https://github.com/midhatn/phoenix-npu-pqc.git`
* **Validation Harness**: `tools/validate_fresh_clone.ps1`
* **Environment**: Windows 11 Pro 64-bit on AMD Phoenix APU (Ryzen 7 7840HS / XDNA1 NPU1)

---

## 2. Release Gate Verdicts

| Release Gate | Verdict | Evidence / Summary |
| :--- | :---: | :--- |
| **PRESENTATION** | **PASS** | Repository structure, existing badges, ASCII topology diagrams, math formulas, and styling preserved. Quick Start expanded with clear operational boundaries, copy-paste commands, and troubleshooting. |
| **FRESH-CLONE HOST SETUP** | **PASS** | Genuinely cloned from remote into clean directory with spaces. Python environment and 42 contract modules verified (42 passed, 0 failed, 0 hardware required). |
| **FRESH-CLONE NPU EXECUTION** | **SELF_REPORTED_UNVERIFIED** | Core primitives (FIPS 202, FIPS 203, FIPS 204, ETSI QKD 014) executed on target silicon and matched independent oracle bit-exactly. Classified as `SELF_REPORTED_UNVERIFIED` pending driver-level dispatch corroboration per repository policy. |
| **CUSTOMER OFFLINE NPU READINESS** | **NO-GO** | Core primitives and 8 extension deliverables (DR21, DR22, DR30, DR31, DR34, DR36, DR38, DR42) validated on physical silicon or formal SMT; full-roadmap gate marked NO-GO strictly due to 2 extension milestones remaining in active quarantine under the Three-Strike Rule (DR39, DR41). |

---

## 3. Evaluated System & Tested Environment

All evaluations were performed on physical AMD Phoenix client silicon:

* **Host Operating System**: Microsoft Windows 11 Pro 64-bit (Build 26200; floor 22621 / 22H2)
* **Processor (APU)**: AMD Ryzen 7 7840HS with Radeon 780M Graphics (8 cores / 16 threads)
* **Target Coprocessor**: AMD XDNA1 NPU1 / AIE2 (`PCI\VEN_1022&DEV_1502`, PnP Problem Code `CM_PROB_NONE`)
* **AMD NPU Driver**: `32.0.20102.3930` (via AMD IPU Driver package)
* **Python Runtime**: CPython 3.13.15 x64 (`ironenv`)
* **XRT Windows SDK**: Release 2.21.75 (`ccc244c2c423588972ade76142cdc01049477aaa39a35be97e782b97eb7c5295`), Runtime 2.21.0
* **MLIR-AIE (IRON)**: v1.4.1 wheel (`a3a0266051cbeb7bd28c0304d02fa361b3c05036c81f0880a0046992a77e7663`, commit `3ca0193cea9e`)
* **Native Toolchain**: Microsoft Visual Studio 2022 Build Tools (MSVC v143, Clang/LLVM, Windows 11 SDK)

---

## 4. Fresh-Clone Validation Methodology

The validation tool (`tools/validate_fresh_clone.ps1`) was developed to enforce strict reproducibility:

1. **Remote-Only Cloning**: Executes `git clone --quiet <RepoUrl> <Destination>` directly from GitHub. Shared local clones and copy operations are rejected.
2. **Path Quoting & Spaces**: Tested against destination directory paths containing whitespace (e.g. `C:\Projects\clean clone candidate\`).
3. **Fail-Closed Destination Safety**: Rejects existing non-empty destination directories with exit code 1 to avoid accidental clobbering.
4. **Environment Isolation**: Executes commands against the designated Python runtime without machine-wide pollution.
5. **Sanitization & Redaction**: Automatically strips private user directories and machine-identifying personal paths from all generated reports.

---

## 5. Candidate Branch Validation

* **Source Branch**: `docs/clean-clone-release-readiness`
* **Tested Commit**: Candidate HEAD
* **Test Directory**: `C:\Projects\clean clone candidate\`

### 5.1 Host-Only Preflight Test

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\validate_fresh_clone.ps1 `
    -Destination "C:\Projects\clean clone candidate" `
    -Ref "docs/clean-clone-release-readiness" `
    -HostOnly
```

* **Command Exit Code**: `0`
* **Execution Duration**: ~22.4 seconds
* **Modules Evaluated**: 42 modules
* **Passed**: 42
* **Failed**: 0
* **Hardware Access**: Disabled (Host CPU validation only)

### 5.2 Canonical Physical Silicon Suite

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\validate_fresh_clone.ps1 `
    -Destination "C:\Projects\clean clone candidate" `
    -Ref "docs/clean-clone-release-readiness" `
    -Hardware
```

* **Command Exit Code**: `0`
* **Target Hardware**: AMD Phoenix NPU (`VEN_1022 DEV_1502`)
* **Core PQC Results**:
  * DR0 (Ring Product): Bit-exact match across 24 test cases.
  * DR1 (ML-DSA-44 RejNTT): Bit-exact match across 33 test cases.
  * DR2d (ML-KEM-512 K-PKE KeyGen): Bit-exact match across 25 official ACVP vectors.
  * DR3–DR8 (ML-KEM Suite): Bit-exact match across all official test vectors.
  * DR9 (FIPS 202 SHA-3/SHAKE): Bit-exact match across 122 test vectors.
  * DR11–DR15 (ML-DSA Suite): Bit-exact match across 255 ACVP test cases.
  * DR18 (Dual-Key Combiner): Bit-exact match across 25 test cases.

---

## 6. Published-Main Acceptance Validation

* **Published Branch**: `main`
* **Target Ref**: `origin/main`
* **Test Directory**: `C:\Projects\clean clone published\`

The validation script was repeated against the published default branch following PR merge:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\validate_fresh_clone.ps1 `
    -Destination "C:\Projects\clean clone published" `
    -Ref "main" `
    -HostOnly
```

* **Command Exit Code**: `0`
* **Host Preflight Modules**: 42 of 42 modules completed successfully
* **Integrity / Policy Findings**: 0 blocking, 0 warnings

---

## 7. Known Blockers, Quarantined Modules & Technical Limitations

In accordance with the repository's Kernel Integrity Policy and Zero-Speculation rules:

1. **Physical Corroboration**: Physical dispatches are observed and verified bit-exact through the configured XRT runtime. Independent hardware-level register/ETW tracing remains open (`PHYSICAL-DISPATCH-CORROBORATION`), so claims are labeled `SELF_REPORTED_UNVERIFIED`.
2. **Quarantined Milestones**: Following the remediation of 8 extension deliverables (DR21, DR22, DR30, DR31, DR34, DR36, DR38, DR42), only two (2) deliverables remain in active quarantine under the Three-Strike Rule:
   * DR39 (dudect Side-Channel Timing: missing unprivileged cycle counter `get_cycles()`)
   * DR41 (Quantum Key Management / Q-KMS: discrete user-mode graph dispatches re-initialize tile state; persistent sealed hardware enclave in SRAM across separate dispatches unsupported in user-mode XRT)
3. **Core & Remediated Readiness**: Core lattice PQC (FIPS 202, FIPS 203, FIPS 204), hybrid QKD combiner (ETSI GS QKD 014 / NIST SP 800-56C), and 8 remediated extension deliverables (DR21, DR22, DR30, DR31, DR34, DR36, DR38, DR42) are verified on target hardware or via formal Z3 SMT proofs.

---

## 8. Artifact & Evidence References

* **Validation Script**: [`tools/validate_fresh_clone.ps1`](../../tools/validate_fresh_clone.ps1)
* **Customer Acceptance Runbook**: [`customer_demo/OFFLINE_RUNBOOK.md`](../../customer_demo/OFFLINE_RUNBOOK.md)
* **Customer Go/No-Go Decision Matrix**: [`customer_demo/GO_NO_GO.md`](../../customer_demo/GO_NO_GO.md)
* **Master Silicon Runner**: [`run_all_silicon_tests.py`](../../run_all_silicon_tests.py)
* **Host Preflight Runner**: [`run_all_pqc_tests.py`](../../run_all_pqc_tests.py)
