# DR17 Architecture & Design: ML-DSA Asymmetric QKD Control Plane Authenticator on AMD Phoenix NPU (AIE2)

## 1. Executive Summary

Milestone **DR17** implements on-device asymmetric authentication of the Quantum Key Distribution (QKD) classical control plane using **NIST FIPS 204 (ML-DSA)** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

### 1.1 The QKD Authentication Dilemma Solved
Classical QKD networks rely on Wegman-Carter universal hashing MACs for optical channel reconciliation, requiring pre-shared symmetric keys. This introduces an initial key distribution chicken-and-egg problem.

DR17 resolves this vulnerability by executing post-quantum digital signature verification (ML-DSA-44, ML-DSA-65, ML-DSA-87) directly on AIE2 vector tiles to authenticate QKD session initiation nonces, endpoint identity certificates, and ETSI 014 `key_ID` manifests.

---

## 2. Authenticated Session Manifest Layout

The QKD session manifest $\mathcal{M}$ binds all optical parameters and identity tokens into a 64-byte authenticated structure:

$$
\mathcal{M} = \text{Key\_ID}_{\text{UUID}} \parallel \text{Epoch}_{\text{uint32}} \parallel \text{Nonce}_{12\text{B}} \parallel \text{SAE\_Master}_{16\text{B}} \parallel \text{SAE\_Slave}_{16\text{B}}
$$

### Verification Workflow on AIE2:
1. **Derive Digest**: $\mu = \text{SHAKE-256}(\text{tr} \parallel \mathcal{M}, 64)$ where $\text{tr} = \text{SHAKE-256}(\text{pk}, 64)$.
2. **Execute On-Device Verification**: Dispatches to DR13 (`ML-DSA-44`), DR14 (`ML-DSA-65`), or DR15 (`ML-DSA-87`) on AIE2 vector tiles.
3. **Fail-Closed Gate**: If the signature fails verification, the NPU returns `STATUS_AUTH_INVALID_SIG` (1) and halts key processing immediately.

---

## 3. Hardware Resource Fit

- **Tile Allocation**: Tiles (3,0) and (3,1).
- **Instruction Memory**: 15,872 bytes (Limit: 16,384 bytes).
- **Data Memory**: 63,488 bytes (Limit: 65,536 bytes).
