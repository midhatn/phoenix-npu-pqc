# DR28 Research and Citation Provenance: NIST SP 800-208 / RFC 8554 LMS Stateless Verification

## Milestone Deliverable Context
- Deliverable: **DR28 (NIST SP 800-208 / RFC 8554 LMS Stateless Verification Engine)**
- Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- Objective: Provide stateless on-tile verification of Leighton-Micali Signatures (LMS/HSS) for immutable secure boot and bitstream authentication without leaf-state corruption risk.

## Citation Ledger

### Citation 1: NIST Special Publication 800-208
- Source Title: Recommendation for Stateful Hash-Based Signature Schemes
- Author / Organization: D. Cooper, D. Apon, Q. Dang, M. Davidson, M. Dworkin, C. Miller (NIST)
- URL: https://csrc.nist.gov/publications/detail/sp/800-208/final
- Publication Date: October 2020
- Exact Technical Principles:
  - Formally approves LMS (RFC 8554) for US Federal agency code signing and secure boot firmware verification.
  - Verification is completely stateless and safe against rollback or state-reuse attacks; stateful private key management is strictly isolated to offline HSM signers.
- Implementation Impact: Implemented on-tile stateless signature verifier strictly scoped to public verification routines.

### Citation 2: IETF RFC 8554: Leighton-Micali Hash-Based Signatures
- Source Title: Leighton-Micali Hash-Based Signatures
- Author / Organization: D. McGrew, M. Curcio, S. Fluhrer (Cisco Systems, IETF RFC 8554)
- URL: https://www.rfc-editor.org/rfc/rfc8554.html
- Publication Date: April 2019
- Exact Technical Principles:
  - Algorithm 4b: `lm_ots_verify` candidate public key reconstruction from one-time signature chains.
  - Algorithm 6b: `lms_verify` Merkle tree path traversal from leaf node $T[2^h + q]$ to root $T[1]$.
  - Hash prefixes: D_PKEY (0x0080), D_INTR (0x0081), D_LEAF (0x0082) with 16-byte identifier $I$ and 4-byte leaf index $q$.
- Implementation Impact: Implemented on-tile LM-OTS candidate leaf recovery and binary Merkle tree traversal on AMD Phoenix AIE2.
