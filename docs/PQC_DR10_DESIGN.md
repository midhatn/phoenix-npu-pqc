# DR10 Architecture & Design: Entropy/Key-Source & Sealed-Lifecycle Architecture on AMD Phoenix NPU (AIE2)

## 1. Executive Summary

Milestone **DR10** establishes the 100% on-device entropy conditioning, external key source authentication, and sealed-state inter-operation lifecycle architecture for post-quantum cryptographic operations on the AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2).

DR10 guarantees that secret keys, randomness seeds, derived intermediate key tokens, and plaintexts remain strictly confined within tile-local SRAM (L1) across chained operations, eliminating host memory leakage.

---

## 2. Supported Ingress Modes & Lifecycle Architecture

### 2.1 Mode 0: External Raw Ingress & On-Chip Conditioning
- **Contract**: The host supplies raw unconditioned entropy (64 bytes) via DMA.
- **On-Device Derivation**: The NPU performs domain-separated cryptographic conditioning on-chip via SHA3-256:

$$
K_{\text{session}} = \text{SHA3-256}(\text{entropy} \parallel \text{domain\_id} \parallel \text{epoch})
$$
- The derived session key is directly stored in the tile-resident sealed session register.

### 2.2 Mode 2: Authenticated External / QKD Key Material Ingress
- **Contract**: External key distribution material (e.g. from Quantum Key Distribution - QKD networks or external HSMs) enters through an authenticated ingress adapter.
- **On-Device Verification**:
  1. **Magic Verification**: Header magic `b"QKD1"`.
  2. **Domain Separation**: Bound to target cryptographic domain (e.g., `DOMAIN_MLKEM_768`, `DOMAIN_MLDSA_44`).
  3. **Freshness / Replay Protection**: Verifies monotonic epoch counter (`req_epoch >= current_epoch`).
  <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr10_design; classification=SELF_REPORTED_UNVERIFIED] -->
  4. **Authentication Tag**: Computes constant-time SHA3-256 MAC over the header and key material.
  5. **Fail-Closed Isolation**: Upon any verification mismatch, the tile immediately zeroizes all secret state and returns an error status (`kBadAuthTag`, `kDomainMismatch`, or `kEpochStale`).

### 2.3 Mode 3: Idempotent Sealed Session Teardown & Zeroization
- Closes the active session and cryptographically erases all tile SRAM registers (`is_active = 0`, `domain_id = 0`, `key_material = [0]*64`).

---

## 3. Hardware Resource Fit

- **Kernel Footprint**: Compiled under 10 KiB instruction memory (well within 16 KiB hardware limit).
- **Stack & Tile Data**: 8 KiB stack allocation with zeroization on terminal exit.
