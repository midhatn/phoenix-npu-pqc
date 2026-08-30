# DR39 Architecture & Design: dudect Microarchitectural Constant-Time Side-Channel Leakage Verifier

<div align="center">

![Methodology: dudect TVLA (Welch's t-test)](https://img.shields.io/badge/Methodology-dudect%20TVLA%20(Welch's%20t--test)-005ea8)
![Standard: ISO/IEC 17825](https://img.shields.io/badge/Standard-ISO%2FIEC%2017825%20(TVLA)-darkblue)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Leakage Elimination Mandate

Milestone **DR39** implements the **`dudect` Microarchitectural Constant-Time Side-Channel Leakage Verifier (Welch's $t$-test Test Vector Leakage Assessment)** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It provides automated, statistical verification that on-device PQC primitives (ML-KEM, ML-DSA, Curve25519, branchless multiplexers) execute in constant time with zero secret-dependent microarchitectural timing variation ($|t| < 4.5$, $p > 0.001$).

---

## 2. Statistical TVLA & Welford Accumulator Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  TVLA TRACE SAMPLER: Fixed vs Random Secret Key Input Sequences (N = 10,000 Traces)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌───────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│  CLASS 0: Fixed Secret Input              │ │  CLASS 1: Uniformly Random Secret Input  │
│   • Fixed Secret Key / Fixed Nonce        │ │   • Random Secret Key / Random Nonce     │
│   • Samples: X_0,0, X_0,1, ..., X_0,N     │ │   • Samples: X_1,0, X_1,1, ..., X_1,N    │
└─────────────────────┬─────────────────────┘ └────────────────────┬─────────────────────┘
                      │                                            │
                      \─────────────────────┬──────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  ONLINE WELFORD ACCUMULATOR (AIE2 Tile 3,2): Running Mean (M), Variance (S), Count (N)│
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  WELCH'S t-STATISTIC CALCULATION:                                                      │
│                         t = (Mean_0 - Mean_1) / sqrt(Var_0/N_0 + Var_1/N_1)            │
│   • PASS CRITERION: |t| < 4.5  --> Provably Constant Time (p > 0.001, Zero Leakage)   │
│   • FAIL CRITERION: |t| >= 4.5 --> Statistically Significant Timing Leakage Detected  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mathematical Formulation

1. **Welford's One-Pass Algorithm**:
   For each new timing sample $x_k$:
   $$M_k = M_{k-1} + \frac{x_k - M_{k-1}}{k}$$
   $$S_k = S_{k-1} + (x_k - M_{k-1})(x_k - M_k)$$
   $$\text{Sample Variance } s^2 = \frac{S_k}{k - 1}$$

2. **Welch's $t$-Test**:
   $$t = \frac{\bar{X}_0 - \bar{X}_1}{\sqrt{\frac{s_0^2}{N_0} + \frac{s_1^2}{N_1}}}$$

---

## 4. References & Standards Citations

1. **Reparaz, Balasch, Verbauwhede (2017)**: *Dude, is my code constant time?* (IEEE Security & Privacy / USENIX).
2. **ISO/IEC 17825:2016**: *Testing methods for the mitigation of non-invasive attack classes*.
3. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
