# DR20 Architecture & Design: QKDN Interoperability & Master Silicon Certification Suite on AMD Phoenix NPU (AIE2)

## 1. Executive Summary

Milestone **DR20** establishes the master automated validation harness and interoperability test architecture for **Quantum Key Distribution Networks (QKDN)** and Post-Quantum Cryptography across all 23 hardware gates on the AMD Phoenix NPU.

DR20 validates compliance with **ITU-T Y.3800–Y.3804**, **ISO/IEC 23837-1/2**, and **NIST ACVP**.

---

## 2. Certification Architecture (Gates 00 to 22)

The master test runner (`run_all_silicon_tests.py`) orchestrates:
1. **Foundation Arithmetic (DR0)**: Negacyclic ring products on vector SIMD.
2. **Matrix Samplers & Noise (DR1, DR2a, DR2b, DR2c)**: ExpandA, SampleNTT, CBD3.
3. **PKE & KEM Primitives (DR2d, DR3, DR4, DR5, DR6, DR7, DR8)**: Full FIPS 203 ML-KEM-512/768/1024.
4. **FIPS 202 Services (DR9)**: SHA-3/SHAKE permutation core.
5. **Sealed Memory Isolation (DR10)**: Hardware memory scrubbing.
6. **Digital Signatures (DR11, DR12, DR13, DR14, DR15)**: Full FIPS 204 ML-DSA-44/65/87.
7. **Hybrid QKD Defense-in-Depth (DR16, DR17, DR18, DR19)**: ETSI 014 Ingress, ML-DSA QKD Auth, SP 800-56C Combiner, and Full-Duplex Session Orchestrator.
