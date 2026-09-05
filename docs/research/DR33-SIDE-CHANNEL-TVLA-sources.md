# DR33 Research and Provenance: Side-Channel Power/EM Trace Acquisition & TVLA Framework

## Milestone Deliverable Context
- Deliverable: **DR33 (Physical Side-Channel Power/EM Trace Acquisition & TVLA Leakage Evaluation Framework for Phoenix AIE2)**
- Standards: NIST SP 800-140F, ISO/IEC 17825:2016 / 2024, NIST NIAT TVLA Methodology
- Hardware: AMD Phoenix NPU (AIE2 / XDNA1, 20-tile array)
- Classification & Integrity Rules:
  - Strict compliance with `AGENTS.md` and `zero-speculation-policy.md`.
  - Truthful boundary labeling: Host timing or process counters must never be claimed as physical power or EM traces.
  - AIE2 hardware provides dedicated trigger and execution-marker packet emission via ObjectFifo DMA channels to synchronize with external physical acquisition equipment (oscilloscopes, EM near-field probes).
  - Software evaluation framework provides mathematically rigorous Welch's t-test TVLA statistical engine ($|t| > 4.5$ threshold) over fixed-vs-random trace matrices.

## Citation Ledger

### Citation 1: NIST SP 800-140F: CMVP Approved Non-Invasive Attack Mitigation Test Metrics
- Source Title: CMVP Approved Non-Invasive Attack Mitigation Test Metrics: Recommendations of the National Institute of Standards and Technology
- Author / Organization: National Institute of Standards and Technology (NIST), U.S. Department of Commerce
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/140/f/final
- Publication Date: 2020-03-24
- Access Date: 2026-09-05T14:52:00Z
- Relevant Section: Section 4 (Approved Metrics) & Appendix B (Test Vector Leakage Assessment)
- Exact Technical Claim:
  - Test Vector Leakage Assessment (TVLA) using Welch's two-sample t-test is an approved non-specific leakage assessment metric for detecting physical side-channel vulnerability in cryptographic modules.
  - Test vectors must be partitioned into fixed and pseudo-random subsets, evaluated across aligned time-series trace points.
  - Decision threshold: $|t| > 4.5$ indicates statistically significant leakage rejecting the null hypothesis with confidence $p < 0.00001$.
- How Claim Was Independently Verified: Verified mathematically against Welch-Satterthwaite two-sample t-statistic formulas and standard statistical test distributions.
- Affected Files: `phoenix_sdr_dsp/pqc/dr33_side_channel_tvla_abi.py`, `tests/test_pqc_dr33_contract.py`.
- Confidence Level: PRIMARY

### Citation 2: ISO/IEC 17825:2016 / ISO/IEC 17825:2024: Non-Invasive Attack Mitigation Testing
- Source Title: Information technology — Security techniques — Testing methods for the mitigation of non-invasive attack classes against cryptographic modules
- Author / Organization: International Organization for Standardization (ISO) / International Electrotechnical Commission (IEC)
- Source Type: Normative standard
- Full URL: https://www.iso.org/standard/60867.html
- Publication Date: 2016-01-15 (revised 2024)
- Access Date: 2026-09-05T14:52:00Z
- Relevant Section: Clause 6 (Power and Electromagnetic Analysis Testing), Clause 6.4 (TVLA methodology)
- Exact Technical Claim:
  - Defines non-invasive testing protocols requiring strict hardware trigger synchronization for power and EM acquisition.
  - Requires measurement of points of interest across cryptographic operations (key scheduling, polynomial arithmetic, Montgomery reductions, masking gadgets).
  - Specifies fixed-versus-random and random-versus-random baseline tests to isolate genuine cryptographic leakage from environmental/instrumentation artifacts.
- How Claim Was Independently Verified: Verified against published side-channel evaluation criteria and hardware trigger protocol specifications.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr33_side_channel_tvla_service.cc`, `phoenix_sdr_dsp/pqc/dr33_side_channel_tvla_abi.py`.
- Confidence Level: PRIMARY

### Citation 3: Goodwill et al. (Cryptography Research Inc. / Rambus, 2011)
- Source Title: A testing methodology for side-channel resistance based on Test Vector Leakage Assessment (TVLA)
- Authors: Gilbert Goodwill, Benjamin Jun, Josh Jaffe, Pankaj Rohatgi
- Organization: Cryptography Research Inc. (CRI) / Rambus
- Source Type: Peer-reviewed conference technical report (NIST NIAT 2011)
- Full URL: https://csrc.nist.gov/csrc/media/events/non-invasive-attack-testing-workshop/documents/08_goodwill.pdf
- Publication Date: 2011-09-29
- Access Date: 2026-09-05T14:52:00Z
- Relevant Section: Pages 3-12 (Statistical foundations of TVLA, Welch's t-test formulation)
- Exact Technical Claim:
  - The Welch t-statistic $t = \frac{\bar{X}_1 - \bar{X}_2}{\sqrt{\frac{s_1^2}{N_1} + \frac{s_2^2}{N_2}}}$ does not assume equal sample variances.
  - Running sample statistics (mean and variance) can be calculated online using Welford's algorithm to avoid numerical instability and excessive memory consumption during large trace acquisitions ($N \ge 10^5$).
- How Claim Was Independently Verified: Validated Welford algorithm recurrence equations: $M_{k} = M_{k-1} + (x_k - M_{k-1})/k$, $S_k = S_{k-1} + (x_k - M_{k-1})(x_k - M_k)$.
- Affected Files: `phoenix_sdr_dsp/pqc/dr33_side_channel_tvla_abi.py`.
- Confidence Level: PRIMARY

### Citation 4: Repository Side-Channel Rigor Policy
- Source Title: Agent Directive: Hardware Ground Truth and Zero-Fabrication Engineering
- Source Type: Repository policy (`AGENTS.md` & `zero-speculation-policy.md`)
- Relevant Section: "Side-channel rigor" & "Execution labels"
- Exact Technical Claim:
  - "TVLA claims require valid fixed-versus-random trace acquisition and statistical analysis. Host timing or process counters are not a substitute for physical power/EM traces."
  - "Never use 'side-channel secure', 'constant-time', 'DPA resistant', or 'fault resistant' without bounded supporting evidence."
  - Distinguishes `[ON-TILE SILICON]` (hardware trigger emission on AIE2) from `[HOST RUNTIME]` (TVLA statistical processing).
- How Claim Was Independently Verified: Enforced via automated scanner `tools/agent_integrity.py` and strict code labeling.
- Affected Files: All DR33 files.
- Confidence Level: PRIMARY
