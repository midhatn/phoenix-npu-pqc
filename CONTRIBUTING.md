# Contributing to Phoenix NPU PQC & QKD

Thank you for your interest in contributing to **Phoenix NPU PQC & QKD**! This project is an open-source, peer-reproducible academic research initiative aimed at accelerating finalized Post-Quantum Cryptography standards (NIST FIPS 202, 203, 204) and Quantum Key Distribution protocols (ETSI GS QKD 014, NIST SP 800-56C) directly on AMD Phoenix NPU (AIE2 / XDNA1 Architecture) silicon.

---

## 1. Code of Conduct & Academic Integrity

* All code contributions must be submitted under the repository's standard Apache License 2.0. Any external reference algorithms must specify an immutable upstream URL and revision.
* Cryptographic implementations must be mathematically verifiable against official NIST ACVP (Automated Cryptographic Validation Protocol) vectors and ETSI technical specifications.
* Any empirical hardware claims must include complete benchmark logs and physical silicon execution reproduction steps.

---

## 2. Universal Architecture Invariants

Every pull request modifying or introducing cryptographic kernels or hardware dataflow graphs **MUST** strictly adhere to the four non-negotiable architectural invariants:

1. **Zero Host Cryptographic Fallback**:
   * All polynomial arithmetic, NTT/INTT butterflies, modular reductions, Centered Binomial Distribution sampling, rejection loops, SHA-3/SHAKE sponge absorb/squeeze steps, and multi-key combiners must execute **100% on AIE2 compute tiles**.
   * The host CPU must never perform fallback cryptographic calculations or repairs.
2. **DMA Channel Limits & Ingress**:
   * Exactly 2 input DMA channels (`request_in`, `descriptor_in`) and 1 output DMA channel (`result_out`) per core boundary. Exactly 2 host DMA fills per operation.
3. **Terminal-Only Egress**:
   * Intermediate secrets ($K_{\text{QKD}}$, $K_{\text{PQC}}$, sponge states, nonces) must remain sealed inside tile SRAM. Only final public records (status codes, signatures, ciphertexts, derived keys, and CRC32 checksums) may transfer to CPU DDR upon completion.
4. **Fail-Closed Semantics & Zeroization**:
   * All intermediate arrays and stack buffers inside C++ kernels must be explicitly zeroized prior to function return.
   * Host-side staging buffers must be cleared with `_clear_host_staging()` inside `finally:` blocks.

---

## 3. Hardware Resource Budgets

All native C++ Peano LLVM-AIE kernels must conform to the physical AIE2 compute tile constraints:
* **Instruction Memory (`.text`)**: Strictly **< 16 KiB** (16,384 bytes) per worker tile.
* **Local Data SRAM**: Strictly **< 64 KiB** (65,536 bytes) per worker tile.
* **Stack Size**: Maximum `0x2000` (8 KiB) per worker.

---

## 4. Local Development & Silicon Validation Workflow

### Prerequisites
* Windows 11 64-bit or Linux with AMD NPU driver installed.
* AMD Ryzen 7 7840HS / 7940HS / 8840HS / 8945HS APU with XDNA1 NPU.
* MLIR-AIE (IRON) toolchain with Peano LLVM-AIE compiler and XRT runtime.

### Step-by-Step Validation
```powershell
# 1. Clone your fork
git clone https://github.com/<your-username>/phoenix-npu-pqc.git
cd phoenix-npu-pqc

# 2. Run master 23-gate silicon test suite
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" run_all_silicon_tests.py

# 3. Run ETSI GS QKD 014 live integration test
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" tests/pqc_device_resident/test_idq_etsi014_qkd_silicon.py
```

---

## 5. Submitting a Pull Request (PR)

1. Fork the repository and create a new feature branch (`git checkout -b feature/dr21-fips205-slhdsa`).
2. Follow the standard repository structure:
   * **C++ Kernel**: Place under `phoenix_sdr_dsp/pqc/kernels/`.
   * **AIE2 Hardware Graph**: Place under `phoenix_sdr_dsp/pqc/`.
   * **Silicon Test**: Place under `tests/pqc_device_resident/`.
   * **Design Doc**: Add `docs/PQC_DRxx_DESIGN.md`.
   * **Validation Doc**: Add `docs/PQC_DRxx_SILICON_VALIDATION_<DATE>.md`.
3. Verify that `run_all_silicon_tests.py` achieves **100% PASS** on physical hardware.
4. Push your branch and open a Pull Request with a clear description and silicon test execution log.

---

## 6. Citation & Attribution

If you utilize this codebase or hardware designs in academic work, please cite according to `CITATION.cff` and [`README.md`](README.md#7-formal-academic--standards-citations).
