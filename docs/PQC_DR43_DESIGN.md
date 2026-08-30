# DR43 Architecture & Design: NIST SP 800-90B Continuous Hardware Health & Repetition/Adaptive Tests (ID Quantique / QRNG Integration)

<div align="center">

![Standard: NIST SP 800-90B](https://img.shields.io/badge/Standard-NIST%20SP%20800--90B%20(Section%204.4)-005ea8)
![Standard: BSI AIS 31 (PTG.2/PTG.3)](https://img.shields.io/badge/Standard-BSI%20AIS%2031%20Online%20Alarms-purple)
![Industry: ID Quantique QRNG Alignment](https://img.shields.io/badge/Industry-ID%20Quantique%20QRNG%20Alignment-darkgreen)
![Hardware: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Target-AMD%20Phoenix%20NPU%20(AIE2%20%2F%20XDNA1)-red)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Health Monitoring Mandate

Milestone **DR43** implements the **NIST SP 800-90B Continuous Hardware Health & Repetition/Adaptive Tests (ID Quantique / QRNG Integration)** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

It establishes an online, zero-overhead continuous health monitor operating on live entropy streams from the DR27 QRNG reservoir and physical silicon entropy sources. It executes the **Repetition Count Test (RCT)** and the **Adaptive Proportion Test (APT)** directly on AIE2 hardware before entropy can be consumed by lattice key generation.

---

## 2. Continuous Health Monitor Pipeline

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  LIVE PHYSICAL NOISE / QRNG STREAM: S_0, S_1, S_2, ..., S_k (Raw 8-bit Bytes)          │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
┌───────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│  REPETITION COUNT TEST (RCT)              │ │  ADAPTIVE PROPORTION TEST (APT)          │
│   • Evaluates stuck-at constant patterns  │ │   • Sliding window W = 512 samples       │
│   • Cutoff C = 1 + ceil(-log2(W)/H_min)   │ │   • Counts occurrences of sample S_base  │
│   • For H_min >= 7.0, Cutoff C = 4        │ │   • Cutoff C_apt = 1 + CritBinom(...)    │
│   • Repetitions >= C --> ALARM TRIP       │ │   • Occurrences >= C_apt --> ALARM TRIP  │
└─────────────────────┬─────────────────────┘ └────────────────────┬─────────────────────┘
                      │                                            │
                      \─────────────────────┬──────────────────────/
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  CONTINUOUS HEALTH STATE MONITOR (AIE2 Tile 2,2):                                      │
│   • HEALTHY (0x01)       --> Entropy stream accepted into DR27 reservoir               │
│   • ALARM_TRIPPED (0x02) --> Instantaneous Fail-Closed Lock & Memory Zeroization (0x00)│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mathematical Cutoff Calculations (NIST SP 800-90B Section 4.4)

1. **Repetition Count Test (RCT)**:
   For false positive probability $\alpha = 2^{-20}$ and estimated min-entropy $H_{\text{min}} = 7.0\text{ bits/byte}$:
   $$C = 1 + \left\lceil \frac{-\log_2(\alpha)}{H_{\text{min}}} \right\rceil = 1 + \left\lceil \frac{20}{7.0} \right\rceil = 1 + 3 = 4$$
   If any 8-bit symbol repeats $\ge 4$ consecutive times, RCT triggers an immediate hardware alarm.

2. **Adaptive Proportion Test (APT)**:
   For window size $W = 512$ and $H_{\text{min}} = 7.0$:
   $$p = 2^{-H_{\text{min}}} = 2^{-7} = \frac{1}{128}$$
   Using the binomial tail cutoff for $\alpha = 2^{-20}$, $C_{\text{apt}} = 16$.
   If the target symbol occurs $\ge 16$ times in the 512-sample window, APT triggers an immediate hardware alarm.

---

## 4. References & Standards Citations

1. **NIST SP 800-90B (2018)**: *Recommendation for the Entropy Sources Used for Random Bit Generation* (Section 4.4 Continuous Health Tests).
2. **BSI AIS 31 (2022)**: *A Proposal for Functionality Classes for Random Number Generators* (PTG.2 / PTG.3 Online Alarms).
3. **ID Quantique (IDQ)**: *Quantis Quantum Random Number Generator Health Architecture*.
4. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
