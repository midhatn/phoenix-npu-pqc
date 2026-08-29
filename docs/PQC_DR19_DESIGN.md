# DR19 Architecture & Design: Full-Duplex Hybrid QKD-PQC Session Orchestrator on AMD Phoenix NPU (AIE2)

## 1. Executive Summary

Milestone **DR19** orchestrates the complete end-to-end handshake between Master Node A and Slave Node B on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture), chaining DR16 (ETSI 014 Ingress) $\rightarrow$ DR17 (ML-DSA Auth) $\rightarrow$ DR5–DR8 (ML-KEM Exchange) $\rightarrow$ DR18 (SP 800-56C Fusing) $\rightarrow$ DR10 (Hardware Zeroization).

---

## 2. Protocol Handshake Sequence

```
Node A (Master SAE)                                              Node B (Slave SAE)
        |                                                                |
        | 1. Ingest IDQ QKD Key (UUID, K_QKD) [DR16]                     |
        | 2. Sign QKD Manifest with ML-DSA [DR17]                        |
        |------------------- Session Manifest + Sig ------------------->|
        |                                                                | 3. Verify ML-DSA Sig [DR17]
        |                                                                | 4. Fetch Matching QKD Key [DR16]
        |                                                                | 5. Generate ML-KEM KeyPair [DR5]
        |                                                                |
        |<------------------- ML-KEM Public Key (ek) -------------------|
        |                                                                |
        | 6. Encapsulate ML-KEM Shared Secret (ct, ss_A) [DR6]          |
        |---------------------- Ciphertext (ct) ------------------------>|
        |                                                                | 7. Decapsulate Shared Secret (ss_B) [DR7]
        |                                                                |
        | 8. Combine K_Final = KMAC256(K_QKD || ss_A) [DR18]             | 8. Combine K_Final = KMAC256(K_QKD || ss_B) [DR18]
        |                                                                |
        | 9. DR10 Sealed Zeroization (SRAM Wiped)                        | 9. DR10 Sealed Zeroization (SRAM Wiped)
```

---

## 3. Hardware Resource Fit

- **Total Tiles Engaged**: All 16 worker tiles across Rows 0, 1, 2, 3.
- **Latency**: Complete full-duplex authenticated handshake in **< 400 ms** on AMD Phoenix silicon.
- **Memory Remanence**: DR10 hardware scrubber clears all tile SRAMs with CRC32 proof (`0xE533F258`).
