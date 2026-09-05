# Offline Customer Demonstration Runbook: AMD Phoenix NPU PQC

**Document Version:** 1.0.0  
**Target Hardware:** AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)  
**Security Standard:** Zero CPU Cryptographic Fallback, Zero Internet Connection Required  

---

## 1. System Requirements & Hardware Prerequisites

Before beginning the offline customer demonstration, verify that the host laptop satisfies the following hardware and software requirements:

1. **Host Processor & NPU:** AMD Ryzen 7 7840HS, Ryzen 9 7940HS, or Ryzen 7 Pro 7840U with integrated XDNA1 / AIE2 Neural Processing Unit (PCI ID `1502`, BDF `0066:00:01.1`).
2. **Operating System:** Windows 11 Pro / Enterprise (x64), Build 22631 or later.
3. **Driver Status:** AMD IPU Driver installed and healthy (`AMD IPU Device` status `OK`, Problem Code `0`, `CM_PROB_NONE`).
4. **Local Runtime Dependencies (Pre-Vendored):**
   - IRON Python Environment: `third_party\mlir-aie\ironenv\Scripts\python.exe` (Python 3.13 / MLIR-AIE).
   - XRT Windows SDK: `third_party\xrt_windows_sdk\xrt_sdk\xrt` (DLLs and headers).
   - Compiled AIE2 Device Artifacts: Pre-built `.xclbin`, `insts.bin`, and `.pdi` binaries.
   - Official Test Vectors: Vendored NIST ACVP / CAVP JSON vectors under `tests/` and `schemas/`.
5. **Strict Offline Environment:**
   - No internet access, package download, or remote server connection is required or allowed during the execution.
   - Disconnecting Wi-Fi or enabling Airplane Mode is recommended to prove complete offline autonomy.

---

## 2. Pre-Demo Verification Procedure

Before presenting to the customer, run the offline package verification script to validate local file hashes, hardware health, and environment integrity.

### Invocation:
Open PowerShell 7 or Windows PowerShell as Administrator or standard user and execute:

```powershell
powershell -ExecutionPolicy Bypass -File .\customer_demo\verify_offline_package.ps1
```

### Expected Output:
```text
================================================================================
PHOENIX NPU PQC OFFLINE PACKAGE PREFLIGHT VERIFICATION
================================================================================
[INFO] Verifying Git repository status...
[PASS] Clean worktree confirmed on branch audit/customer-critical-readiness.
[INFO] Verifying AMD Phoenix NPU hardware presence...
[PASS] Found AMD IPU Device (PCI\VEN_1022&DEV_1502). Status: OK (ProblemCode: 0).
[INFO] Verifying local Python interpreter and IRON runtime...
[PASS] IRON Python interpreter located: third_party\mlir-aie\ironenv\Scripts\python.exe.
[INFO] Verifying pre-compiled AIE2 XCLBIN artifacts...
[PASS] All 24 canonical AIE2 XCLBIN artifacts present and SHA-256 verified.
[INFO] Verifying official NIST ACVP/CAVP test vector files...
[PASS] All official NIST KAT vector files present with intact hashes.
[INFO] Verifying offline isolation...
[PASS] Zero network dependencies required; dry-run resolution succeeded.
================================================================================
OFFLINE PACKAGE INTEGRITY: VERIFIED (READY FOR DEMO)
================================================================================
```

---

## 3. Customer Demonstration Execution Procedure

To execute the offline customer demonstration, invoke `run_customer_npu_pqc_demo.ps1` with the mandatory `-Offline` and `-StrictNpu` switches.

### Invocation:
```powershell
powershell -ExecutionPolicy Bypass -File .\customer_demo\run_customer_npu_pqc_demo.ps1 -Offline -StrictNpu
```

### Switches Explained:
- `-Offline`: Actively verifies that no outbound network requests are initiated and all dependencies resolve locally.
- `-StrictNpu`: Strictly enforces zero CPU cryptographic fallback. Any NPU allocation failure, dispatch timeout, or hardware exception immediately causes a fail-closed non-zero exit.

---

## 4. Sequence of Demonstration Stages

The demonstration script executes the following ten (10) sequential verification stages:

1. **Stage 1: NPU Device Identity & Health Check:**
   - Queries `Get-PnpDevice` for AMD IPU Device.
   - Records PCI BDF, device hardware IDs, driver version, and current error code.
2. **Stage 2: Source Commit & Artifact Hash Provenance:**
   - Verifies the Git HEAD commit SHA-256 and records loaded XCLBIN artifact identities.
3. **Stage 3: Forced-NPU-Failure Negative Test (Zero-Fallback Proof):**
   - Deliberately dispatches with an invalid device selector or corrupted artifact header.
   - Verifies that the implementation fails closed immediately without returning any cryptographic result or falling back to CPU.
4. **Stage 4: NIST FIPS 202 SHA-3 & SHAKE Acceleration (DR9):**
   - Executes SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, and SHAKE256 on the AIE2 Keccak permutation core.
   - Validates complete digests against official NIST CAVP vectors.
5. **Stage 5: NIST FIPS 203 ML-KEM-512 / 768 / 1024 Complete Pipelines (DR2d, DR3–DR8):**
   - Executes K-PKE KeyGen, Encrypt, Decrypt, and complete ML-KEM KeyGen, Encaps, and Decaps on AIE2 hardware.
   - Exercises the branch-free Fujisaki-Okamoto transform and implicit rejection on malformed ciphertexts.
6. **Stage 6: NIST FIPS 204 ML-DSA-44 / 65 / 87 Complete Pipelines (DR1, DR11–DR15):**
   - Executes RejNTT matrix expansion, KeyGen, Sign, and Verify on AIE2 hardware tiles.
   - Validates all $(k, l)$ parameter dimensions across ML-DSA-44, ML-DSA-65, and ML-DSA-87 against NIST ACVP KAT vectors.
7. **Stage 7: NIST SP 800-56C Dual Key Combiner (DR18):**
   - Ingresses dual secret inputs into AIE2 tile SRAM and executes two-step feedback key derivation.
8. **Stage 8: Independent Frozen Expected Output Verification:**
   - Compares 100% of the complete device output buffers against frozen independent vectors without any CPU cryptographic computation on the test path.
9. **Stage 9: Tamper & Negative Verification:**
   - Submits single-bit flipped signatures, wrong public keys, and corrupted ciphertexts to the NPU.
   - Confirms that the device strictly rejects invalid inputs.
10. **Stage 10: Canonical Regression Suite & Honest Denominator Accounting:**
    - Runs the canonical silicon regression suite (24 gates / 857 cases).
    - Accounts for all 10 quarantined deliverables, proving that no defective shortcut is counted towards customer acceptance.

---

## 5. Troubleshooting & Hardware Recovery

If an unexpected driver error, hardware stall, or timeout occurs:

1. **Check NPU PnP Status:**
   ```powershell
   Get-PnpDevice -FriendlyName "*NPU*" | Select-Object FriendlyName, Status, Problem, ConfigManagerErrorCode
   ```
2. **Hardware Reset Policy:**
   - **DO NOT** attempt to uninstall drivers or edit Windows Registry settings.
   - Perform a clean Windows restart:
     ```powershell
     Restart-Computer
     ```
3. **Post-Reboot Verification:**
   - Upon reboot, re-run `verify_offline_package.ps1` to confirm clean hardware recovery.
   - Re-launch `run_customer_npu_pqc_demo.ps1 -Offline -StrictNpu`.
