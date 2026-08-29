# DR9 Architecture & Design: Reusable NIST FIPS 202 NPU Service (SHA3-224/256/384/512 & SHAKE128/256)

## 1. Executive Summary

Milestone **DR9** provides a complete, reusable, on-device NIST FIPS 202 cryptographic service on the AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2). It exposes all six standard FIPS 202 permutation-based functions:
- **SHA3-224** ($r = 144$ bytes, $d = 28$ bytes output)
- **SHA3-256** ($r = 136$ bytes, $d = 32$ bytes output)
- **SHA3-384** ($r = 104$ bytes, $d = 48$ bytes output)
- **SHA3-512** ($r = 72$ bytes, $d = 64$ bytes output)
- **SHAKE128** ($r = 168$ bytes, arbitrary variable-length XOF output)
- **SHAKE256** ($r = 136$ bytes, arbitrary variable-length XOF output)

---

## 2. Microarchitecture & Algorithmic Design

### 2.1 Sponge Construction & State Management
- **State Array**: 1600-bit (200-byte) internal Keccak state represented as an 8-byte aligned array of 25 64-bit lanes.
- **Multi-Block Absorb**: Streaming absorption of arbitrary-length input messages up to buffer capacity (2048 bytes per request) using tile-local Keccak-f[1600] rounds.
- **Exact Domain Suffix & 10*1 Padding**:
  - SHA3 functions: Suffix byte `0x06`
  - SHAKE functions: Suffix byte `0x1F`
  - Bit-exact pad10*1 alignment across multi-rate boundaries.
- **Multi-Block Squeeze**: Arbitrary variable-length XOF squeeze (up to 1024 bytes per response packet) with automatic permutation execution across rate boundaries.

---

## 3. Protocol & Ingress/Egress Contract

- **Ingress Transfer 1 (Request Buffer, 2048 B)**: Raw input message bytes.
- **Ingress Transfer 2 (Descriptor Buffer, 16 B)**:
  - Byte 0..3: Magic `b"\x01\x71\x52\x00"`
  - Byte 4: Function ID (1: SHA3-224, 2: SHA3-256, 3: SHA3-384, 4: SHA3-512, 5: SHAKE128, 6: SHAKE256)
  - Byte 5: Operation (`0x01` = Digest/Squeeze)
  - Byte 6: Milestone (`0x09` = DR9)
  - Byte 8..11: Request ID (`uint32`)
  - Byte 12..13: Message Length (`uint16`)
  - Byte 14..15: Squeeze Output Length (`uint16`)
- **Egress Transfer (Result Buffer, 1044 B)**:
  - Header: Magic `0x4839524D` (`b"MR9H"`), Request ID, Status Code (`0` = OK), Output Digest Length, Hardware CRC32.
  - Payload: Squeezed digest output bytes.

---

## 4. Hardware Resource Compliance

- **Kernel ELF**: Compiled with Peano AIE2 ELF compiler under 12 KiB instruction footprint (well below the 16 KiB hardware limit).
- **Stack & Memory**: Strict 8 KiB stack allocation (`stack_size=0x2000`) with explicit zeroization of internal Keccak state upon terminal completion.
