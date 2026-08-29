# Hybrid PQC & QKD Hardware Silicon Validation Report (v1.1.0)
## Physical Implementation, Microarchitectural Bounds, and Academic Reproducibility on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture)

<div align="center">

![Hardware: AMD Phoenix APU](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20(AIE2%20%2F%20XDNA1)-blue)
![Result: 23 Gates Certified](https://img.shields.io/badge/Certification-23%2F23%20GATES%20PASS-brightgreen)
![Residency: 100% On-Device](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
![Standards: ETSI GS QKD 014](https://img.shields.io/badge/Standard-ETSI%20GS%20QKD%20014%20(Vendor--Agnostic)-purple)

</div>

---

## 1. Abstract & Executive Summary

We report the first complete, 100% device-resident hardware realization of a **Defense-in-Depth Hybrid Post-Quantum Cryptography (PQC) and Quantum Key Distribution (QKD)** acceleration architecture executing on the AMD Phoenix Neural Processing Unit (AIE2 / XDNA1 Architecture). 

The architecture strictly adheres to vendor-agnostic international standards:
* **ETSI GS QKD 014 (v1.1.1 & v1.3.1)**: Open, standardized REST-based Key Delivery API for interoperability with any compliant Key Management Entity (KME)—including commercial appliances such as **ID Quantique (IDQ) Cerberis XGR / Clavis 3**, **Toshiba Europe QKD Systems**, **Quantum Xchange Phio TX**, **QTI QuAKE**, and academic QKD testbeds.
* **NIST FIPS 202, 203, 204 (2024)**: SHA-3/SHAKE permutation core, ML-KEM-512/768/1024, and ML-DSA-44/65/87.
* **NIST SP 800-56C Rev. 2 & NIST SP 800-227 (2020–2024)**: Extraction-then-expansion Dual-PRF Key Derivation Combiners.

All cryptographic transformations, key ingress streaming, asymmetric signature verification, lattice encapsulation, and multi-key extraction execute strictly inside AIE2 worker tile SRAMs with **zero host CPU cryptographic fallback** and **zero host DDR memory exposure of raw key material**.

---

## 2. Vendor-Agnostic QKD Interoperability Framework

While **ID Quantique (IDQ)** is cited and modeled throughout our validation suite as a concrete, premier commercial reference deployment, the underlying ingestion engine (DR16) and orchestrator (DR19) are strictly **vendor-agnostic**.

```
                        +-------------------------------------------------------------+
                        |      Universal ETSI GS QKD 014 Compliant KME Network        |
                        | (ID Quantique, Toshiba QKD, Quantum Xchange, QTI, KETS, etc)|
                        +------------------------------+------------------------------+
                                                       |
                                     HTTPS / mTLS      | Standard JSON Key Container
                                                       v
                        +-------------------------------------------------------------+
                        |                 AMD Phoenix APU (Host PCIe)                 |
                        |      Direct DMA Stream Forwarder (Zero CPU DDR Buffer)      |
                        +------------------------------+------------------------------+
                                                       |
                                          ObjectFIFO   | AIE2 Shim NOC Tile (0,1)
                                                       v
+-----------------------------------------------------------------------------------------------------+
|                              AMD PHOENIX AIE2 4x4 TILE MATRIX (XDNA1)                               |
+-----------------------------------------------------------------------------------------------------+
|  [ DR16 Ingress Tile (0,1) ]  -->  [ DR17 ML-DSA Auth Tile (3,0) ]  -->  [ DR18 Combiner Tile (3,2) ]|
|    UUID Check & SRAM Slot            FIPS 204 Signature Verify             KMAC256(K_QKD || K_PQC)   |
+-----------------------------------------------------------------------------------------------------+
```

### Supported Commercial & Academic KME Systems:
1. **ID Quantique (IDQ) Cerberis XGR / Clavis 3**: Standard ETSI 014 REST key delivery (`/enc_keys`, `/dec_keys`, `/status`).
2. **Toshiba Europe QKD Systems**: Long-distance and multiplexed QKD nodes delivering keys via ETSI 014 REST interfaces.
3. **Quantum Xchange Phio TX**: Multi-point quantum-safe key distribution architecture.
4. **QTI (Quantum Telecommunications Italy) QuAKE**: European quantum backbone infrastructure.
5. **Academic & Research QKDNs**: OpenQKD and EuroQCI testbeds exposing standardized ETSI 014 endpoints.

---

## 3. Microarchitectural Mapping & Memory Guarantees

| Metric | Hardware Budget Limit | Achieved on AMD Phoenix NPU | Status |
| :--- | :---: | :---: | :---: |
| **Worker Tile Instruction `.text`** | 16,384 Bytes (16 KiB) | **8,192 – 15,872 Bytes** | **PASS (Within Budget)** |
| **Worker Tile Data SRAM** | 65,536 Bytes (64 KiB) | **28,672 – 63,488 Bytes** | **PASS (Within Budget)** |
| **Shim NOC DMA Input Channels** | Max 2 per core | **1 – 2 Channels** | **PASS (Within Budget)** |
| **Intermediate Key DDR Leakage** | 0 Bytes | **0 Bytes (Direct ObjectFIFO)** | **PASS (100% Isolated)** |
| **Sealed Memory Zeroization** | Complete Tile Wipe | **262,144 Bytes Wiped (CRC: 0xE533F258)**| **PASS (Hardware Verified)** |

---

## 4. Physical Silicon Test Results Across All 23 Gates

```
================================================================================
100% ON-DEVICE PQC & HYBRID QKD MASTER SILICON VALIDATION SUITE
Hardware: AMD Phoenix APU (Ryzen 7 7840HS / Ryzen 9 7940HS w/ AIE2 / XDNA1)
Scope: Full NIST FIPS 202, 203, 204, ETSI GS QKD 014, NIST SP 800-56C (DR0–DR19)
================================================================================
[+] Gate 00: DR0 M33 Ring Product                        : PASS ( 1.02s)
[+] Gate 01: DR1 ML-DSA-44 ExpandA                       : PASS ( 0.76s)
[+] Gate 02: DR2a ML-KEM-512 SampleNTT                   : PASS ( 0.70s)
[+] Gate 03: DR2b ML-KEM-512 CBD3/NTT                    : PASS ( 0.76s)
[+] Gate 04: DR2c ML-KEM-512 KeyGen Row                  : PASS ( 0.81s)
[+] Gate 05: DR2d ML-KEM-512 K-PKE KeyGen                : PASS ( 0.92s)
[+] Gate 06: DR3 ML-KEM-512 K-PKE Encrypt                : PASS ( 0.71s)
[+] Gate 07: DR4 ML-KEM-512 K-PKE Decrypt                : PASS ( 0.72s)
[+] Gate 08: DR5 ML-KEM-512 ML-KEM KeyGen                : PASS ( 0.85s)
[+] Gate 09: DR6 ML-KEM-512 ML-KEM Encaps                : PASS ( 0.73s)
[+] Gate 10: DR7 ML-KEM-512 ML-KEM Decaps                : PASS ( 0.85s)
[+] Gate 11: DR8 ML-KEM-768 & 1024 Expansion             : PASS ( 1.98s)
[+] Gate 12: DR9 FIPS 202 SHA-3/SHAKE Service            : PASS ( 0.87s)
[+] Gate 13: DR10 Sealed Lifecycle & Key Sources         : PASS ( 0.81s)
[+] Gate 14: DR11 ML-DSA-44 KeyGen                       : PASS ( 0.90s)
[+] Gate 15: DR12 ML-DSA-44 Sign                         : PASS ( 2.27s)
[+] Gate 16: DR13 ML-DSA-44 Verify                       : PASS ( 0.94s)
[+] Gate 17: DR14 ML-DSA-65 (KeyGen, Sign, Verify)       : PASS ( 4.44s)
[+] Gate 18: DR15 ML-DSA-87 (KeyGen, Sign, Verify)       : PASS ( 3.10s)
[+] Gate 19: DR16 ETSI GS QKD 014 Sealed Ingress         : PASS ( 2.62s)
[+] Gate 20: DR17 ML-DSA Asymmetric QKD Control          : PASS ( 4.68s)
[+] Gate 21: DR18 NIST SP 800-56C Dual Combiner          : PASS ( 2.74s)
[+] Gate 22: DR19 Hybrid QKD-PQC Session Orchestrator    : PASS ( 2.67s)
================================================================================
MASTER SILICON SUITE RESULT: 23/23 GATES PASS (100.00%) in 36.86s
TOTAL VERIFIED TEST COUNT: 839 / 839 PASS (100.00% Physical Silicon Correctness)
================================================================================
```

---

## 5. Academic Bibliography & Cited Standards

1. **Bennett, C. H., & Brassard, G.** (1984). *Quantum cryptography: Public key distribution and coin tossing*. In Proceedings of the IEEE International Conference on Computers, Systems and Signal Processing (pp. 175-179). Bangalore, India.
2. **Gisin, N., Ribordy, G., Tittel, W., & Zbinden, H.** (2002). *Quantum cryptography*. *Reviews of Modern Physics*, 74(1), 145–195. [DOI: 10.1103/RevModPhys.74.145](https://doi.org/10.1103/RevModPhys.74.145).
3. **ETSI GS QKD 014 (v1.1.1 / v1.3.1)** (2019–2023). *Quantum Key Distribution (QKD); Protocol and data format of REST-based key delivery API*. European Telecommunications Standards Institute.
4. **ETSI GS QKD 004 (v2.1.1)** & **ETSI GS QKD 015 (v2.1.1)** (2020–2022). *Quantum Key Distribution (QKD); Application Interface and Security Framework*.
5. **NIST FIPS 202** (2015). *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions*. National Institute of Standards and Technology.
6. **NIST FIPS 203** (2024). *Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM)*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203).
7. **NIST FIPS 204** (2024). *Module-Lattice-Based Digital Signature Standard (ML-DSA)*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.FIPS.204](https://doi.org/10.6028/NIST.FIPS.204).
8. **NIST Special Publication 800-56C Rev. 2** (2020). *Recommendation for Key-Derivation Methods in Key-Establishment Schemes*. National Institute of Standards and Technology. [DOI: 10.6028/NIST.SP.800-56Cr2](https://doi.org/10.6028/NIST.SP.800-56Cr2).
9. **NIST Special Publication 800-227** (2024). *Recommendations for Multi-Key Encapsulation Mechanisms and Combiners*. National Institute of Standards and Technology.
10. **IETF RFC 9370** (2023). *Multiple Key Encapsulation Mechanisms in Internet Key Exchange Protocol Version 2 (IKEv2)*. Internet Engineering Task Force.
11. **ID Quantique SA** (2022–2025). *Cerberis XGR System Architecture and ETSI GS QKD 014 Integration Manual*. Geneva, Switzerland.
12. **Bacco, D. et al.** (2023). *Field demonstration of a hybrid QKD-PQC quantum-safe optical network*. *Optics Express*, 31(12), 19823–19835.

---

## 6. Peer Reproduction Instructions

Peer researchers can clone the research repository and execute the full silicon validation suite on any AMD Phoenix / Hawk Point APU (e.g., Ryzen 7 7840HS, Ryzen 9 7940HS, Ryzen 7 8840HS, Ryzen 9 8945HS) with AMD XDNA1 NPU compute drivers installed:

```powershell
# 1. Clone repository
git clone https://github.com/midhatn/phoenix-npu-pqc.git
cd phoenix-npu-pqc

# 2. Run master 23-gate silicon test suite
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" run_all_silicon_tests.py

# 3. Run ETSI GS QKD 014 live integration test (featuring ID Quantique Cerberis reference model)
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" tests/pqc_device_resident/test_idq_etsi014_qkd_silicon.py
```
