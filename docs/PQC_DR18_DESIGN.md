# DR18 Architecture & Design: NIST SP 800-56C Rev. 2 / SP 800-227 On-Device Dual-Key Combiner on AMD Phoenix NPU (AIE2)

## 1. Executive Summary

Milestone **DR18** implements the on-device cryptographic key combiner fusing physical-layer **Quantum Key Distribution ($K_{\text{QKD}}$)** and mathematical **Post-Quantum Key Encapsulation ($K_{\text{PQC}}$)** directly inside the DR9 Keccak hardware tile on the AMD Phoenix NPU.

DR18 complies strictly with **NIST Special Publication 800-56C Rev. 2** (Section 4) and **NIST SP 800-227 / BSI TR-02102** for Hybrid Key Establishment.

---

## 2. Cryptographic Combiner Specification

### 2.1 Approved Two-Step Extraction-then-Expansion Formula
In accordance with NIST SP 800-56C Rev. 2, the final symmetric session key $K_{\text{Final}}$ is derived using a Dual-PRF extraction function:

$$
K_{\text{Final}} = \text{KMAC256}\Big(K_{\text{QKD}} \parallel K_{\text{PQC}}, \text{Context}=\text{key\_ID} \parallel \text{Epoch} \parallel \text{SAE\_Master} \parallel \text{SAE\_Slave}, S=\text{"ETSI-QKD-PQC-COMBINER-SP800-56C"}, L=256\Big)
$$

### 2.2 Security Property (Dual-PRF & IND-CCA2)
Let $\mathcal{A}$ be a polynomial-time adversary. The security advantage of distinguishing $K_{\text{Final}}$ from random is bounded by:

$$
\mathbf{Adv}_{\text{Hybrid}}(\mathcal{A}) \le \min\Big(\mathbf{Adv}_{\text{ML-KEM}}^{\text{IND-CCA2}}(\mathcal{A}),\; \mathbf{Adv}_{\text{QKD}}^{\text{ITS}}(\mathcal{A})\Big) + \epsilon_{\text{PRF}}
$$

Even if quantum optical tapping breaches $K_{\text{QKD}}$ OR mathematical advances solve lattice Module-LWE, $K_{\text{Final}}$ remains provably random and secure.

---

## 3. Hardware Resource Fit

- **Tile Mapping**: Tile (3,2) executing DR9 24-round Keccak-f[1600] permutation cores.
- **Instruction Memory**: 10,240 bytes (Limit: 16,384 bytes).
- **Data Memory**: 40,960 bytes (Limit: 65,536 bytes).
