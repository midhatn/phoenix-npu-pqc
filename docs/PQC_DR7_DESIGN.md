# DR7 Design: On-Device ML-KEM-512 ML-KEM.Decaps (NIST FIPS 203 Algorithm 17)

## 1. Scope & Objective

DR7 implements the complete, device-resident **ML-KEM-512 Decapsulation** algorithm ($	ext{ML-KEM.Decaps}$) as specified in **NIST FIPS 203 Algorithm 17**, executing 100% on the **AMD Phoenix Ryzen 7040 / 8040 NPU** (XDNA1 architecture / AIE2 tile array).

<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr7_design; classification=SELF_REPORTED_UNVERIFIED] -->
The decapsulation procedure securely decapsulates the shared secret key $K \in \{0, 1\}^{256}$ from a received ciphertext $c \in \{0, 1\}^{768 	imes 8}$ using the decapsulation key $dk \in \{0, 1\}^{1632 	imes 8}$, employing Fujisaki-Okamoto (FO) re-encryption verification and branchless implicit rejection.

```
+-------------------------------------------------------------------------------------------------------------+
|                                    NIST FIPS 203 Algorithm 17 (ML-KEM.Decaps)                               |
|                                                                                                             |
|  Input: dk = (dk_PKE || ek || H(ek) || z) in B^{1632}, c in B^{768}                                         |
|  Output: Shared key K in B^{32}                                                                             |
|                                                                                                             |
|  1. m' <- K-PKE.Decrypt(dk_PKE, c)                                                                          |
|  2. (K_bar', r') <- G(m' || H(ek))                                                                          |
|  3. K_bar <- J(z || c, 32) = SHAKE256(z || c, 32)                                                           |
|  4. c' <- K-PKE.Encrypt(ek, m', r')                                                                         |
|  5. if c == c' then return K_bar' else return K_bar (branchless selection)                                 |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 2. 6-Worker Spatial Pipeline Architecture

To conform to the 16 KiB program memory and 64 KiB local data memory constraints of each physical AIE2 tile, the computation is distributed across a 6-worker linear spatial pipeline:

```
[Host DMA In]
      | (Request: dk[1632] || c[768], Descriptor: 16 B)
      v
+------------------+  Tile (0,2): Worker 0 (K-PKE.Decrypt)
| Worker 0:        |  - K-PKE.Decrypt(dk_PKE, c) -> m' (32 B)
| Decrypt Tile     |  - Low-stack scoped NTT & INTT computation
+------------------+  - Forwards m', H(ek), z, rho, c, t_hat into Derivation Token (1968 B)
      |
      v
+------------------+  Tile (1,2): Worker 1 (Noise Sampling)
| Worker 1:        |  - G(m' || H(ek)) = SHA3-512(m' || H(ek)) -> (K_bar', r')
| Noise Sampler    |  - Sample r'_0, r'_1 (CBD3 + NTT)
+------------------+  - Sample e'_1,0, e'_1,1 (CBD2), e'_2 + mu(m') (CBD2 + Decompress_1)
      |               - Packs Noise Token (4464 B)
      v
+------------------+  Tile (2,2): Worker 2 (Matrix Row 0 & Rejection Key)
| Worker 2:        |  - Expand A^T[0,0], A^T[0,1] via SampleNTT(rho)
| Row 0 Expand     |  - Compute Rejection Key K_bar = SHAKE256(z || c, 32)
+------------------+  - Packs Col0 Token (5488 B)
      |
      v
+------------------+  Tile (3,2): Worker 3 (Row 0 Accumulation)
| Worker 3:        |  - u'_0 = INTT(A^T[0,0] * r'_0 + A^T[0,1] * r'_1) + e'_1,0
| Row 0 Accumulate |  - Compress_10(u'_0) -> u'_0 (320 B)
+------------------+  - Packs U0 Token (4272 B)
      |
      v
+------------------+  Tile (4,2): Worker 4 (Matrix Row 1 Expand)
| Worker 4:        |  - Expand A^T[1,0], A^T[1,1] via SampleNTT(rho)
| Row 1 Expand     |  - Packs Col1 Token (5296 B)
+------------------+
      |
      v
+------------------+  Tile (5,2): Worker 5 (Finalize & FO Selection)
| Worker 5:        |  - u'_1 = INTT(A^T[1,0] * r'_0 + A^T[1,1] * r'_1) + e'_1,1 -> Compress_10 (320 B)
| Finalize Tile    |  - v' = INTT(t_hat[0] * r'_0 + t_hat[1] * r'_1) + (e'_2 + mu) -> Compress_4 (128 B)
+------------------+  - Branchless comparison: diff = c ^ (u'_0 || u'_1 || v')
            |               - Branchless select: K = (diff == 0) ? K_bar' : K_bar
      v               - CRC32 verification and terminal packet creation (52 B)
[Host DMA Out]
```

---

## 3. Worker Program Sizes & Hardware Budgets

All kernels are compiled using `clang++ -O2 --target=aie2-none-unknown-elf` with loop-unroll controls. Every worker fits safely under the 16,384-byte AIE2 instruction memory budget:

| Worker | Source File | Function | Compiled Size | Limit | Headroom |
|---|---|---|---|---|---|
| **Worker 0** | `dr7_mlkem512_decaps_decrypt.cc` | $	ext{K-PKE.Decrypt}$ | **12,496 B** | 16,384 B | 3,888 B (23.7%) |
| **Worker 1** | `dr7_mlkem512_decaps_noise.cc` | SHA3-512 $G$, CBD3/2, $\mu$ | **14,240 B** | 16,384 B | 2,144 B (13.1%) |
| **Worker 2** | `dr7_mlkem512_decaps_row0_expand.cc` | SampleNTT $\mathbf{A}^T[0,*]$, SHAKE256 $ar{K}$ | **6,976 B** | 16,384 B | 9,408 B (57.4%) |
| **Worker 3** | `dr7_mlkem512_decaps_row0_accumulate.cc` | $u'_0$ accumulation & $	ext{Compress}_{10}$ | **8,352 B** | 16,384 B | 8,032 B (49.0%) |
| **Worker 4** | `dr7_mlkem512_decaps_row1_expand.cc` | SampleNTT $\mathbf{A}^T[1,*]$ | **4,480 B** | 16,384 B | 11,904 B (72.7%) |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr7_design; classification=SELF_REPORTED_UNVERIFIED] -->
| **Worker 5** | `dr7_mlkem512_decaps_finalize.cc` | $u'_1, v'$, branchless compare & select | **10,320 B** | 16,384 B | 6,064 B (37.0%) |

---

## 4. Host/Device ABI

- **Request Payload** (`2400 B`): Decapsulation key $dk$ (`1632 B`) $\parallel$ Ciphertext $c$ (`768 B`).
- **Descriptor** (`16 B`): Magic header (`0x527101`), operation code (`0x02`), parameter set (`0x03` = ML-KEM-512, `0x05` = Decaps), request ID.
- **Terminal Sealed Record** (`52 B`):
  - `0x00..0x03`: Magic `0x4737524D` (`b"MR7G"`)
  - `0x04..0x07`: Request ID (`uint32`)
  - `0x08..0x0B`: Status code (`0` = OK)
  - `0x0C..0x0F`: Key length (`32 B`)
  - `0x10..0x13`: CRC32 of 32-byte shared key $K$
  - `0x14..0x33`: Shared key $K \in \{0, 1\}^{256}$
