# DR38 Research and Provenance: Randomness Statistical Battery & NIST SP 800-22 Diagnostic

## Milestone Deliverable Context
- Deliverable: **DR38 (NIST SP 800-22 & BSI AIS 31 Randomness Statistical Test Battery)**
- Standards: NIST SP 800-22 Rev. 1a, BSI AIS 20 / AIS 31, NIST SP 800-90B
- Target Architecture: AMD Phoenix AIE2 / XDNA1 (AIE2 Vector Compute Tiles)
- Classification & Integrity Rules:
  - Kernel Execution: **[ON-TILE SILICON]** for AIE2 hardware dispatch of histogram, bitwise population counting, runs statistics, and nibble poker distribution.
  - Host Harness & Evaluation: **[HOST RUNTIME]** with parent reference oracle comparison and p-value statistical evaluation.
  - Anti-Fabrication Invariant: The statistical accumulator must evaluate 100% of the sample byte buffer on device; no mocked counts, fixed p-values, or precomputed success banners are allowed.
  - Fail-Closed Handling: Degenerate, biased, periodic, or all-zero bitstreams must fail statistical thresholds and be reported truthfully.

## Citation Ledger

### Citation 1: NIST SP 800-22 Rev. 1a - Statistical Test Suite for Random Number Generators
- Source Title: A Statistical Test Suite for Random and Pseudorandom Number Generators for Cryptographic Applications (NIST Special Publication 800-22 Revision 1a)
- Author / Organization: National Institute of Standards and Technology (NIST) / L. E. Bassham III, A. L. Rukhin, J. Soto, J. R. Nechvatal, et al.
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/22/r1/a/final
- Publication Date: 2010-04-01
- Access Date: 2026-09-05T15:30:00Z
- Relevant Section: Section 2.1 (Frequency Monobit Test), Section 2.2 (Block Frequency Test), Section 2.3 (Runs Test), Section 2.4 (Longest Run of Ones Test)
- Exact Technical Claim:
  - The Monobit test assesses whether the number of ones and zeros in a sequence are approximately equal.
  - The Runs test assesses whether the number of runs of ones and zeros of various lengths is as expected for a random sequence.
  - Test statistics derive from sample totals and evaluate against complementary error function and chi-square distributions.
- How Claim Was Independently Verified: Verified against NIST SP 800-22 algorithms and implemented in `dr38_randomness_internal.hpp` and `dr38_randomness_abi.py`.
- Affected Files: `phoenix_sdr_dsp/pqc/dr38_randomness_abi.py`, `phoenix_sdr_dsp/pqc/kernels/dr38_randomness_internal.hpp`.
- Confidence Level: PRIMARY

### Citation 2: BSI AIS 20 / AIS 31 - Functionality Classes for Random Number Generators
- Source Title: A Proposal for: Functionality Classes for Random Number Generators (BSI AIS 20 / AIS 31 Version 2.0)
- Author / Organization: Federal Office for Information Security (BSI Germany) / W. Killmann, W. Schindler
- Source Type: Government technical guideline
- Full URL: https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Zertifizierung/Interpretationen/AIS_31_Functionality_classes_for_random_number_generators_e.pdf
- Publication Date: 2011-09-25
- Access Date: 2026-09-05T15:30:00Z
- Relevant Section: Section 4.3 (Statistical Tests: Test T1 Monobit, Test T2 Poker Test, Test T3 Runs, Test T4 Long Run, Test T8 Shannon Entropy)
- Exact Technical Claim:
  - Test T2 (Poker Test) divides the sequence into 4-bit nibbles and evaluates the chi-square statistic $X = \frac{16}{k} \sum_{i=0}^{15} f_i^2 - k$.
  - Test T8 evaluates Shannon entropy $H = -\sum p_i \log_2(p_i)$ to ensure min-entropy exceeds certified thresholds.
- How Claim Was Independently Verified: Implemented in AIE2 service kernel with bit-exact comparison against independent host reference oracle.
- Affected Files: `phoenix_sdr_dsp/pqc/kernels/dr38_randomness_internal.hpp`, `phoenix_sdr_dsp/pqc/dr38_randomness_abi.py`.
- Confidence Level: PRIMARY

### Citation 3: NIST SP 800-90B - Recommendation for the Entropy Sources Used for Random Bit Generation
- Source Title: Recommendation for the Entropy Sources Used for Random Bit Generation (NIST SP 800-90B)
- Author / Organization: National Institute of Standards and Technology (NIST) / M. S. Turan, E. Barker, J. Kelsey, K. McKay, M. Baish, M. Boyle
- Source Type: Normative standard
- Full URL: https://csrc.nist.gov/pubs/sp/800/90/b/final
- Publication Date: 2018-01-01
- Access Date: 2026-09-05T15:30:00Z
- Relevant Section: Section 4 (Health Tests: Repetition Count Test and Adaptive Proportion Test)
- Exact Technical Claim:
  - Continuous health testing verifies that entropy generation has not suffered catastrophic failure or frozen output.
- How Claim Was Independently Verified: Incorporated continuous sanity checks and health diagnostics into DR38 ABI and test suite.
- Affected Files: `phoenix_sdr_dsp/pqc/dr38_randomness_abi.py`, `tests/test_pqc_dr38_contract.py`.
- Confidence Level: PRIMARY
