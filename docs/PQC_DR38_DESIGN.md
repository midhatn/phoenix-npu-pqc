# DR38 Architecture & Design: NIST SP 800-22 Statistical Randomness Battery & BSI AIS 31 Hardware Suite

<div align="center">

![Standard: NIST SP 800-22 Rev 1a](https://img.shields.io/badge/Standard-NIST%20SP%20800--22%20Rev%201a-005ea8)
![Standard: BSI AIS 20 / AIS 31](https://img.shields.io/badge/Standard-BSI%20AIS%2020%20%2F%20AIS%2031-darkblue)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Quality Mandate

Milestone **DR38** implements the **NIST SP 800-22 Statistical Randomness Battery & BSI AIS 31 Hardware Suite** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It provides hardware-accelerated statistical validation of physical entropy sources (DR27 QRNG reservoir) and on-chip pseudorandom stream generators (DR25 PRNG) to certify entropy quality and detect any physical entropy degradation or hardware tampering before keys are generated.

---

## 2. NIST SP 800-22 & BSI AIS 31 Battery Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  ENTROPY INGRESS: DR27 QRNG Reservoir / DR25 SHAKE PRNG Stream (128 KiB Sample Block) │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  ROW 1 MEMTILES: Shared Scratchpad Ring Buffer (512 KiB / Tile x 4 Columns = 2 MiB)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌───────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│  NIST SP 800-22 STATISTICAL BATTERY       │ │  BSI AIS 31 PHYSICAL RNG BATTERY         │
│   • 1. Frequency (Monobit) Test           │ │   • Test T1: Monobit (9654..10346)       │
│   • 2. Block Frequency Test (M=128)       │ │   • Test T2: Poker Test (Chi-Square)     │
│   • 3. Runs Test (V_obs & p-value)        │ │   • Test T3: Runs Lengths Distribution   │
│   • 4. Longest Run of Ones in a Block     │ │   • Test T4: Long Run Test (Max <= 34)   │
│   • 5. Spectral DFT Test (Peak Heights)   │ │   • Test T8: Shannon Entropy (> 7.98 b/B)│
│   • 6. Approximate Entropy & Cusum        │ └────────────────────┬─────────────────────┘
└─────────────────────┬─────────────────────┘                      │
                      │                                            │
                      \─────────────────────┬──────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  AIE2 HARDWARE BATTERY REPORT: Pass Rate >= 99.0% · Entropy >= 7.99 bits/byte          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Statistical Test Formulations

1. **NIST SP 800-22 Frequency (Monobit) Test**:
   $$S_n = \sum_{i=1}^n X_i, \quad X_i = 2\epsilon_i - 1, \quad s_{\text{obs}} = \frac{|S_n|}{\sqrt{n}}, \quad P\text{-value} = \text{erfc}\left(\frac{s_{\text{obs}}}{\sqrt{2}}\right)$$
   Requirement: $P\text{-value} \ge 0.01$.

2. **BSI AIS 31 Test T2 (Poker Test)**:
   Divides $N=20,000$ bits into $k=5,000$ 4-bit nibbles ($0 \le z < 16$).
   $$X = \frac{16}{5000} \sum_{i=0}^{15} f_i^2 - 5000$$
   Requirement: $1.03 < X < 57.4$ (Passes under $\chi^2$ distribution with 15 degrees of freedom).

3. **BSI AIS 31 Test T8 (Shannon Entropy)**:
   $$H = -\sum_{i=0}^{255} p_i \log_2(p_i) \ge 7.976\text{ bits/byte}$$

---

## 4. References & Standards Citations

1. **NIST SP 800-22 Rev. 1a (2010)**: *A Statistical Test Suite for Random and Pseudorandom Number Generators for Cryptographic Applications*.
2. **BSI AIS 20 / AIS 31 (2011/2022)**: *A Proposal for: Functionality Classes and Evaluation Methodology for Physical Random Number Generators*.
3. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
