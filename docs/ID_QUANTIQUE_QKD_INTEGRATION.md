# ETSI GS QKD 014 Vendor-Agnostic QKD Integration Guide
## Commercial Reference Implementation: ID Quantique (IDQ) Cerberis XGR & Clavis 3

## 1. Architectural Overview

This document specifies the vendor-agnostic integration of **Quantum Key Distribution (QKD)** Key Management Entities (KMEs) with the **AMD Phoenix NPU (AIE2 / XDNA1 Architecture)** via the open international standard **ETSI GS QKD 014 (v1.1.1 & v1.3.1)** ("Protocol and data format of REST-based key delivery API").

While **ID Quantique (IDQ) Cerberis XGR** and **Clavis 3** systems serve as our primary concrete reference implementation, the protocol and binary data model are identical across all ETSI 014 compliant hardware (including **Toshiba Europe QKD Networks**, **Quantum Xchange Phio TX**, **QTI QuAKE**, **KETS Quantum**, and **OpenQKD/EuroQCI** testbeds).

```
                      +-------------------------------------------------------------+
                      |       Universal ETSI GS QKD 014 Compliant KMS Appliance     |
                      |          (e.g., ID Quantique Cerberis, Toshiba QKD, etc.)   |
                      +------------------------------+------------------------------+
                                                     |
                                   HTTPS / mTLS      | ETSI 014 JSON Key Container
                                                     v
                      +-------------------------------------------------------------+
                      |                 AMD Phoenix APU (Host PCIe)                 |
                      |      Direct DMA Stream Forwarder (Zero CPU DDR Buffer)      |
                      +------------------------------+------------------------------+
                                                     |
                                        ObjectFIFO   | AIE2 Shim NOC Tile (0,1)
                                                     v
+---------------------------------------------------------------------------------------------------+
|                            AMD PHOENIX AIE2 4x4 TILE MATRIX (XDNA1)                               |
+---------------------------------------------------------------------------------------------------+
|  [ DR16 Ingress Tile (0,1) ]  -->  [ DR17 ML-DSA Auth Tile (3,0) ]  -->  [ DR18 Combiner Tile (3,2)]|
|    UUID Check & SRAM Slot            FIPS 204 Signature Verify             KMAC256(K_QKD || K_PQC) |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Universal ETSI GS QKD 014 REST API Specification

Every compliant QKD appliance exposes three core REST endpoints over mutual TLS (mTLS):

### 1. Check Key Buffer & KME Status
* **Endpoint**: `GET /api/v1/keys/{slave_sae_id}/status`
* **Response**:
```json
{
  "source_KME_ID": "KME-GENEVA-NODE-01",
  "target_KME_ID": "KME-LAUSANNE-NODE-02",
  "master_SAE_ID": "SAE-NODE-A-NPU",
  "slave_SAE_ID": "SAE-NODE-B-NPU",
  "key_size": 256,
  "stored_key_count": 4096,
  "max_key_count": 8192,
  "max_key_per_request": 128,
  "max_key_size": 1024,
  "min_key_size": 64
}
```

### 2. Request Encryption Keys (Master Node)
* **Endpoint**: `GET /api/v1/keys/{slave_sae_id}/enc_keys?number=1&size=256`
* **Response**:
```json
{
  "keys": [
    {
      "key_ID": "16fb8915-e50e-4212-8c34-a4b780297f8f",
      "key": "Sn+3qB9k2u8vW5zY1mNpQ0rStUvWxYzAbCdEfGhIjKl="
    }
  ]
}
```

### 3. Retrieve Decryption Keys by Key ID (Slave Node)
* **Endpoint**: `POST /api/v1/keys/{master_sae_id}/dec_keys`
* **Request Body**:
```json
{
  "key_IDs": [
    {
      "key_ID": "16fb8915-e50e-4212-8c34-a4b780297f8f"
    }
  ]
}
```

---

## 3. Physical Execution on AMD Phoenix NPU

Researchers can reproduce the complete vendor-agnostic ETSI 014 silicon validation suite (using the ID Quantique Cerberis reference model) on their physical AMD Phoenix hardware using the following command:

```powershell
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\python.exe" tests/pqc_device_resident/test_idq_etsi014_qkd_silicon.py
```

### Verification Outputs:
1. **Direct AIE2 Ingress (Tile 0,1)**: Key material ingests directly into tile memory without touching host CPU cache.
2. **ML-DSA-44 Control Plane Verification (Tile 3,0)**: Asymmetrically signs session nonces and `key_ID` manifests.
3. **NIST SP 800-56C Dual Combiner (Tile 3,2)**: Derives 256-bit AES session key fusing $K_{\text{QKD}}$ and $K_{\text{PQC}}$.
4. **DR10 Zeroization Scrubber (Tile 3,3)**: Clears all intermediate tile SRAM memory to `0x00` upon session close (CRC32: `0xE533F258`).
