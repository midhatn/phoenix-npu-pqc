# DR25 Research and Citation Provenance: Higher-Order Masking & On-Chip Local PRNG Expansion

## Milestone Deliverable Context
- Deliverable: **DR25 (Higher-Order Masking & On-Chip Local PRNG Entropy Expansion)**
- Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- Objective: Mathematical side-channel resistance against Differential Power Analysis (DPA/CPA) and fault injection attacks via 1st- and 2nd-order polynomial blinding and on-tile FIPS 202 SHAKE-128 PRNG entropy expansion.

## Citation Ledger

### Citation 1: Masking Kyber: First- and Higher-Order Masked Decapsulation
- Authors: J. Bos, M. Gourjon, D. Hein, R. Renes, C. van Vredendaal
- Venue / Publication: IACR Transactions on Cryptographic Hardware and Embedded Systems (TCHES), 2021(4), pp. 483-514
- DOI: 10.46586/tches.v2021.i4.483-514
- Exact Technical Principles:
  - Arithmetic masking over the polynomial ring $R_q = \mathbb{Z}_q[X]/(X^N + 1)$ with $N=256, q=3329$.
  - 1st-order masking splits polynomial $s$ into 2 shares ($s = s_0 + s_1 \pmod q$), 2nd-order splits into 3 shares ($s = s_0 + s_1 + s_2 \pmod q$).
  - Linear operations (addition, subtraction, NTT multiplication by public matrices) propagate component-wise across shares: $(A_i + B_i) \pmod q$.
  - Provably secure SNI (Strong Non-Interference) share refreshing gadgets prevent higher-order leakage across sequential operations.
- Implementation Impact: Implemented on-tile 1st- and 2nd-order polynomial blinding, share refreshing, and masked polynomial evaluation on AMD Phoenix AIE2.

### Citation 2: Hardware-Efficient On-Chip Randomness Expansion for Masked Post-Quantum Schemes
- Authors: V. Hwang, J. Koppermann, J. Szefer
- Standards / Publication: FIPS 202 SHAKE-128 / NIST SP 800-90A
- Exact Technical Principles:
  - Continuous share refresh demands massive amounts of fresh randomness, which exhausts external entropy buses and causes memory pipeline stalls.
  - Expanding an external 32-byte QRNG seed directly on-chip inside tile microcode using Keccak-p[1600,24] / SHAKE-128 generates uniform masking coefficients at wire speed without bus traffic.
- Implementation Impact: Implemented on-tile FIPS 202 SHAKE-128 PRNG stream expander with rejection sampling to generate uniform polynomial masks in tile SRAM on AMD Phoenix AIE2.
