# DR40 Architecture & Design: Open Quantum Safe (liboqs / PQClean) Cross-Validation & eBACS Benchmark Harness

<div align="center">

![Standard: Open Quantum Safe (liboqs)](https://img.shields.io/badge/Reference-Open%20Quantum%20Safe%20(liboqs)-005ea8)
![Standard: PQClean KAT Project](https://img.shields.io/badge/Reference-PQClean%20KAT%20Suite-purple)
![Standard: ECRYPT eBACS / SUPERCOP](https://img.shields.io/badge/Benchmark-eBACS%20%2F%20SUPERCOP-darkblue)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Cross-Validation Mandate

Milestone **DR40** implements the **Open Quantum Safe (liboqs / PQClean) Cross-Validation & eBACS Benchmark Harness** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It provides continuous cross-validation against the global reference implementations of NIST Post-Quantum Cryptography (ML-KEM-512/768/1024, ML-DSA-44/65/87, SLH-DSA, LMS) and computes cycle-accurate eBACS performance metrics (`cycles/op`, `ops/sec`) directly on physical AIE2 silicon.

---

## 2. Cross-Validation & Benchmarking Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  OQS / PQClean REFERENCE VECTOR REPOSITORY: Golden Seeds, Plaintexts, & Parameters     │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌───────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│  KNOWN ANSWER TEST (KAT) ENGINE           │ │  eBACS MICROARCHITECTURAL BENCHMARK      │
│   • ML-KEM-512 / 768 / 1024 (Encaps/Decaps│ │   • Cycle counter: 1.0 GHz AIE2 Core Clck│
│   • ML-DSA-44 / 65 / 87 (Sign / Verify)   │ │   • Measures exact cycles/op & ops/sec   │
│   • SLH-DSA-SHAKE-128s / LMS SP 800-208   │ │   • Peak SRAM memory footprint           │
│   • Byte-exact serialization matching     │ └────────────────────┬─────────────────────┘
└─────────────────────┬─────────────────────┘                      │
                      │                                            │
                      \─────────────────────┬──────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  AIE2 CROSS-VALIDATION & PERFORMANCE REPORT: 100% Golden Match · Multi-kOPS Throughput │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported Reference Schemes & Parameter Matrix

| Algorithm | Category | Public Key Size | Secret Key Size | Ciphertext / Sig Size | AIE2 Target Clocks |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **ML-KEM-512** | Lattice KEM | 800 B | 1,632 B | 768 B | ~180,000 cycles |
| **ML-KEM-768** | Lattice KEM | 1,184 B | 2,400 B | 1,088 B | ~250,000 cycles |
| **ML-KEM-1024** | Lattice KEM | 1,568 B | 3,168 B | 1,568 B | ~380,000 cycles |
| **ML-DSA-44** | Lattice Signature | 1,312 B | 2,560 B | 2,420 B | ~420,000 cycles |
| **ML-DSA-65** | Lattice Signature | 1,952 B | 4,032 B | 3,309 B | ~680,000 cycles |
| **ML-DSA-87** | Lattice Signature | 2,592 B | 4,896 B | 4,627 B | ~950,000 cycles |
| **SLH-DSA-128s**| Stateless Hash Signature| 32 B | 64 B | 7,856 B | ~1,200,000 cycles|
| **LMS SHA256-H10**| Stateful Hash Verifier | 56 B | Air-gapped | 1,148 B | ~120,000 cycles |

---

## 4. References & Standards Citations

1. **Open Quantum Safe Project (OQS)**: *liboqs — Open Source C Library for Quantum-Safe Cryptography*.
2. **PQClean Project**: *Clean, portable, memory-safe reference implementations of PQC*.
3. **ECRYPT-CSA / eBACS**: *ECRYPT Benchmarking of All Cryptographic Schemes*.
4. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
