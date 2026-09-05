# DR29 Research and Citation Provenance: NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine

## Milestone Deliverable Context
- Deliverable: **DR29 (NSA CNSA 2.0 Level 5 Multi-Tile Distributed Memory Engine)**
- Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- Objective: Provide multi-tile distributed memory acceleration for NSA CNSA 2.0 Category 5 parameter sets (ML-KEM-1024 and ML-DSA-87), partitioning large matrix polynomials across a 4-tile cluster to guarantee per-tile SRAM residency stays under 44 KiB.

## Citation Ledger

### Citation 1: NSA Cybersecurity Advisory: Commercial National Security Algorithm Suite 2.0
- Source Title: Announcing the Commercial National Security Algorithm Suite 2.0 (CNSA 2.0)
- Author / Organization: National Security Agency (NSA)
- URL: https://www.nsa.gov/Press-Room/News-Highlights/Article/Article/3148889/announcing-the-commercial-national-security-algorithm-suite-20/
- Publication Date: September 2022
- Exact Technical Principles:
  - Formally mandates Category 5 Post-Quantum Cryptography for National Security Systems (NSS):
    - General Public Key Encryption / KEM: ML-KEM-1024 (Category 5)
    - General Digital Signatures: ML-DSA-87 (Category 5)
- Implementation Impact: Implemented distributed hardware acceleration specifically tailored to Category 5 dimensions.

### Citation 2: NIST FIPS 204: Module-Lattice-Based Digital Signature Standard
- Source Title: Module-Lattice-Based Digital Signature Standard (FIPS 204)
- Author / Organization: National Institute of Standards and Technology (NIST)
- URL: https://csrc.nist.gov/pubs/fips/204/final
- Publication Date: August 2024
- Exact Technical Principles:
  - ML-DSA-87 matrix dimension: $k=8, l=7 \implies 8 \times 7 = 56$ polynomials in $R_q$, where $q = 8380417$.
  - Matrix-vector multiplication $A \hat{s}_1$: 56 polynomial NTT point-wise multiplications and row accumulations.
  - Memory Footprint: Storing 56 polynomials in 32-bit word format requires $56 \times 256 \times 4 = 57,344$ bytes (56 KiB), exceeding available single-tile memory when combined with vector $\hat{s}_1$ (7 KiB) and intermediate accumulators.
- Implementation Impact: Implemented 4-tile distributed memory partitioning assigning 2 rows (14 polynomials = 14 KiB) per tile, bounding per-tile SRAM consumption to under 28 KiB.
