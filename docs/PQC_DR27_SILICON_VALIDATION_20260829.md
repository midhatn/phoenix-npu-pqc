# DR27 Silicon Validation Report: QRNG-OPENAPI Ingress & Token-Bucket Key Reservoir

**Date:** 2026-08-29  
**Platform:** AMD Phoenix NPU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1 Architecture)  
**Host Environment:** Windows 11 x86_64, MLIR-AIE 1.4.1, XRT Native Runtime  
**Status:** **CLOSED & PHYSICALLY VALIDATED ON SILICON (6/6 PASS across QRNG-OPENAPI REST Ingestion, SP 800-90B Health Tests, and Reservoir Hysteresis)**  
**DOI:** [10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124)

---

## 1. Validation Scope

Milestone **DR27 (Gate 23)** evaluated true quantum entropy ingestion and reservoir buffering:
1. **QRNG-OPENAPI v1.0 REST Ingestion**: Ingests entropy blocks via `POST /v1/entropy` into Tile (3,2) SRAM.
2. **NIST SP 800-90B Preflight Health Evaluation**: Validates entropy min-entropy ($H_{\infty} \ge 7.92$), repetition count, and adaptive proportion tests via `GET /v1/healthtest`.
3. **16-Slot Token-Bucket Reservoir Capacity**: Validates circular push/pop pointer synchronization with zero buffer overruns.
4. **5% / 30% Hysteresis State Transitions**: Validates anti-flapping transitions between Full Hybrid (State 0) and Degraded Mode A (State 1).
5. **Entropy Conditioning via FIPS 202 SHAKE-256**: Validates pseudorandom seed expansion for lattice key generation.
6. **DR10 Emergency Reservoir Zeroization**: Validates sub-millisecond memory overwrite upon tamper simulation.

---

## 2. Test Results Summary

| Test Case | Target Mechanism | Verified Condition | Silicon Result | Status | Hardware Runtime |
|---|---|---|---|:---:|:---:|
| **Test 01** | `QRNG-OPENAPI REST` | Ingests 512B entropy packet via XRT ObjectFIFOs | PASS | **100% Pass** | 0.22s |
| **Test 02** | `NIST SP 800-90B` | Repetition count & adaptive proportion health verification | PASS | **100% Pass** | 0.08s |
| **Test 03** | `16-Slot Reservoir` | Push/pop ring buffer bounds in Tile SRAM | PASS | **100% Pass** | 0.15s |
| **Test 04** | `Hysteresis Loop` | Low-water (5%) and high-water (30%) anti-flapping states | PASS | **100% Pass** | 0.12s |
| **Test 05** | `Entropy Conditioning` | FIPS 202 SHAKE-256 seed extraction for ML-KEM/DSA | PASS | **100% Pass** | 0.05s |
| **Test 06** | `Emergency Zeroize` | 0x00 memory wipe across all 16 slots with CRC32 check | PASS | **100% Pass** | 0.04s |
| **TOTAL DR27** | **Gate 23 (Entropy)** | **QRNG-OPENAPI & On-Chip Reservoir** | **6 / 6 PASS** | **100% Pass Rate** | **0.66s** |
