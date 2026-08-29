# DR16 Architecture & Design: ETSI GS QKD 014 Key Container Parser & Sealed Ingress on AMD Phoenix NPU (AIE2)

## 1. Executive Summary

Milestone **DR16** implements the 100% on-device key container ingestion and sealed memory management engine for standardized **Quantum Key Distribution (QKD)** optical key streams on the AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2 / XDNA1).

DR16 complies strictly with **ETSI GS QKD 014 (v1.1.1 & v1.3.1)** ("Protocol and data format of REST-based key delivery API") for interoperability with commercial QKD Key Management Entities (KMEs), specifically **ID Quantique (IDQ) Cerberis XGR** and **Clavis 3** appliances.

---

## 2. ETSI GS QKD 014 Data Model & Binary Packing

### 2.1 JSON Key Container Format
In accordance with ETSI GS QKD 014 Clause 6, KME appliances return keys structured in standardized JSON containers:

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

### 2.2 AIE2 ObjectFIFO Binary Layout
The host DMA stream packages the parsed container into sealed AIE2 hardware descriptors:
1. **Descriptor Header (64 Bytes)**:
   - `0..3`: Magic `0x10527101` (DR16 Magic).
   - `4..7`: `request_id` (uint32).
   - `8..11`: `epoch` (uint32 monotonic freshness counter).
   - `12..13`: `key_len` (uint16, 32 or 64 bytes).
   - `14`: Milestone identifier (16).
   - `15`: Flags.
   - `16..31`: UUID-128 binary bytes (16 bytes).
   - `32..63`: Reserved zero padding.
2. **Payload Request (256 Bytes)**:
   - `0..63`: Raw key material $K_{\text{QKD}}$ (up to 64 bytes / 512 bits).
   - `64..95`: Source SAE ID (32 bytes UTF-8).
   - `96..127`: Target SAE ID (32 bytes UTF-8).
   - `128..255`: Reserved zero padding.

---

## 3. Microarchitectural Tile Mapping & Memory Bounds

- **Compute Tile**: Ingress Tile (0,1) with point-to-point DMA streaming.
- **Sealed Storage**: 4-slot ring buffer resident in tile SRAM (`g_sealed_qkd_ring[4][64]`).
- **Memory Footprint**:
  - Instruction `.text`: 8,192 bytes (Limit: 16,384 bytes).
  - Data SRAM: 32,768 bytes (Limit: 65,536 bytes).
- **Zero Host Exposure**: Raw key material $K_{\text{QKD}}$ is consumed directly into AIE2 tile SRAM without CPU memory retention or swap allocation.
