# DR24 Research and Citation Provenance: IPsec/IKEv2 & WireGuard Multi-KEM Tunnel Acceleration

## Milestone Deliverable Context
- Deliverable: **DR24 (Quantum-Safe Kernel-Bypass WireGuard / IPsec Inline VPN Co-Processor / RFC 9370 Multi-KEM)**
- Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- Standards: IETF RFC 9370, RFC 8784, RFC 5869, WireGuard Protocol Specification

## Citation Ledger

### Citation 1: Multiple Key Encapsulation Mechanisms in Internet Key Exchange Protocol Version 2 (IKEv2)
- Source Title: Multiple Key Encapsulation Mechanisms in Internet Key Exchange Protocol Version 2 (IKEv2)
- Author / Organization: V. Smyslov, P. Kampanakis (IETF RFC 9370)
- URL: https://www.rfc-editor.org/rfc/rfc9370.html
- Publication Date: May 2023
- Standards / Release: Proposed Standard RFC 9370
- Exact Technical Principles:
  - Multi-KEM key exchange framework combining traditional Diffie-Hellman with multiple post-quantum KEMs (`IKE_INTERMEDIATE` and `IKE_FOLLOWUP_KE` exchanges).
  - Key derivation logic: recursive combination of shared secrets $SK_d = \text{prf}(SK_{d(n-1)}, K_n | \text{Ni} | \text{Nr})$.
  - Preserves security even if one or more underlying KEM algorithms are broken, guaranteeing quantum resistance.
- Implementation Impact: Implemented AIE2-resident RFC 9370 Multi-KEM key derivation combiner fusing classic ECDH and post-quantum ML-KEM shared secrets with session nonces.

### Citation 2: WireGuard Protocol & Post-Quantum WireGuard (PQ-WireGuard)
- Source Title: WireGuard: Next Generation Kernel Network Tunnel
- Author: Jason A. Donenfeld
- Venue / URL: NDSS 2017 / https://www.wireguard.com/papers/wireguard.pdf
- Related RFC / Work: PQ-WireGuard (Hülsing et al., "Post-quantum WireGuard", IEEE S&P 2021)
- Exact Technical Principles:
  - 1-RTT NoiseIK handshake with post-quantum pre-shared key (PresharedKey / PQ-PSK) injection.
  - Tunnel traffic encryption using ChaCha20-Poly1305 AEAD with 64-bit monotonically increasing sequence numbers for replay protection.
  - Periodic session rekeying (rekey-after-time, rekey-after-messages) without interrupting active tunnel traffic.
- Implementation Impact: Implemented on-tile WireGuard packet encapsulation/decapsulation and multi-KEM rekeying accelerator on AMD Phoenix AIE2.
