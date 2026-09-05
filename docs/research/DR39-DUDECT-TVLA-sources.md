# DR39 Research and Provenance: dudect Timing Leakage & TVLA Diagnostic Engine

## Milestone Deliverable Context
- Deliverable: **DR39 (dudect Timing Leakage & TVLA Diagnostic Engine on AMD Phoenix NPU)**
- Standards: NIST SP 800-140F, ISO/IEC 17825:2016/2024, Reparaz et al. (DATE 2017)
- Target Architecture: AMD Phoenix AIE2 / XDNA1 (AIE2 Vector Compute Tiles)
- Classification & Integrity Rules:
  - Kernel Execution: **[ON-TILE SILICON]** for AIE2 hardware execution of invariant-latency vs variable-latency cryptographic operations, cycle timestamp collection, and differential timing measurement buffers.
  - Host Harness & Evaluation: **[HOST RUNTIME]** for dudect two-sample Welch's t-test evaluation, percentile trimming, higher-order moments, and pass/fail classification.
  - Anti-Fabrication Invariant: No hardcoded t-statistics, simulated cycle counts, or precomputed pass banners. Variable-latency operations must fail closed with $|t| > 4.5$, while verified invariant-latency operations must pass with $|t| \le 4.5$.

## Citation Ledger

### Citation 1: Reparaz et al. (DATE 2017) - dudect Timing Leakage Evaluation
- Source Title: dudect: Timing Leakage Detection via Welch's t-test (DATE 2017)
- Authors: Oscar Reparaz, Josep Balasch, Ingrid Verbauwhede (KU Leuven / imec)
- Source Type: Peer-reviewed conference paper (Design, Automation & Test in Europe, DATE 2017)
- Full URL: https://eprint.iacr.org/2016/1123.pdf
- Publication Date: 2017-03-27
- Access Date: 2026-09-05T15:55:00Z
- Relevant Section: Section 3 (Methodology: Leakage Detection with Welch's t-test), Section 4 (Pre-processing: Truncation and Higher-order Moments)
- Exact Technical Claim:
  - Welch's two-sample t-test detects timing leakage by comparing execution time distributions between two distinct input classes (Class 0 and Class 1).
  - Decision threshold $|t| > 4.5$ rejects the null hypothesis that execution times are independent of secret inputs with confidence $p < 0.00001$.
  - Percentile cropping / truncation of high timing outliers filters out system/DMA interrupts and non-deterministic bus jitter without introducing false negatives.
- How Claim Was Independently Verified: Verified against the published dudect methodology and implemented in `phoenix_sdr_dsp/pqc/dr39_dudect_abi.py` and `phoenix_sdr_dsp/pqc/kernels/dr39_dudect_internal.hpp`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr39_dudect_abi.py`, `phoenix_sdr_dsp/pqc/kernels/dr39_dudect_internal.hpp`, `tests/test_pqc_dr39_contract.py`.
- Confidence Level: PRIMARY

### Citation 2: NIST SP 800-140F: CMVP Approved Non-Invasive Attack Mitigation Test Metrics
- Source Title: CMVP Approved Non-Invasive Attack Mitigation Test Metrics: Recommendations of the National Institute of Standards and Technology
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/140/f/final
- Publication Date: 2020-03-24
- Access Date: 2026-09-05T15:55:00Z
- Relevant Section: Section 4 (Approved Metrics) & Appendix B (Test Vector Leakage Assessment)
- Exact Technical Claim:
  - Non-specific leakage assessment using Welch's t-test evaluates cryptographic module implementations for timing and physical side-channel vulnerability.
  - Test vectors must be partitioned into fixed and pseudo-random subsets, evaluated across aligned execution runs.
  - Decision threshold: $|t| > 4.5$ indicates statistically significant leakage rejecting the null hypothesis with confidence $p < 0.00001$.
- How Claim Was Independently Verified: Verified mathematically against Welch-Satterthwaite two-sample t-statistic formulas: $t = \frac{\bar{X}_0 - \bar{X}_1}{\sqrt{s_0^2/N_0 + s_1^2/N_1}}$.
- Affected Files: `phoenix_sdr_dsp/pqc/dr39_dudect_abi.py`, `tests/test_pqc_dr39_contract.py`.
- Confidence Level: PRIMARY

### Citation 3: ISO/IEC 17825:2016 / 2024: Non-Invasive Attack Mitigation Testing
- Source Title: Information technology — Security techniques — Testing methods for the mitigation of non-invasive attack classes against cryptographic modules
- Author / Organization: International Organization for Standardization (ISO) / International Electrotechnical Commission (IEC)
- Source Type: Normative standard
- Full URL: https://www.iso.org/standard/60867.html
- Publication Date: 2016-01-15 (revised 2024)
- Access Date: 2026-09-05T15:55:00Z
- Relevant Section: Clause 6 (Side-channel analysis testing), Clause 6.4 (TVLA methodology)
- Exact Technical Claim:
  - Specifies fixed-versus-random and random-versus-random baseline tests to isolate genuine cryptographic timing/power leakage from environmental noise.
- How Claim Was Independently Verified: Incorporated fixed-vs-random and class-A-vs-class-B test patterns into DR39 ABI and test suite.
- Affected Files: `phoenix_sdr_dsp/pqc/dr39_dudect_abi.py`, `tests/pqc_device_resident/test_dr39_dudect_silicon.py`.
- Confidence Level: PRIMARY

### Citation 4: Repository Side-Channel Rigor Policy
- Source Title: Agent Directive: Hardware Ground Truth and Zero-Fabrication Engineering
- Source Type: Repository policy (`AGENTS.md` & `zero-speculation-policy.md`)
- Relevant Section: "Side-channel rigor" & "Execution labels"
- Exact Technical Claim:
  - "TVLA claims require valid fixed-versus-random trace acquisition and statistical analysis. Host timing or process counters are not a substitute for physical power/EM traces."
  - "Never use 'side-channel secure', 'constant-time', 'DPA resistant', or 'fault resistant' without bounded supporting evidence."
  - Distinguishes `[ON-TILE SILICON]` (AIE2 execution and cycle-measurement packet generation) from `[HOST RUNTIME]` (dudect Welch's t-test processing).
- How Claim Was Independently Verified: Enforced via automated scanner `tools/agent_integrity.py` and strict code labeling.
- Affected Files: All DR39 files.
- Confidence Level: PRIMARY
