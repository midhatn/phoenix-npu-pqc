# DR8 Architecture & Design: NIST FIPS 203 Parameter-Set Expansion (ML-KEM-768 & ML-KEM-1024)

## 1. Executive Summary

Milestone **DR8** expands the 100% on-device post-quantum cryptography implementation on the AMD Phoenix NPU (Ryzen 7040 / 8040 AIE2) to cover all security categories defined in NIST FIPS 203:
- **ML-KEM-512** ($k=2$, NIST Security Category 1)
- **ML-KEM-768** ($k=3$, NIST Security Category 3)
- **ML-KEM-1024** ($k=4$, NIST Security Category 5)

Like preceding milestones, DR8 enforces **100% device residency** with zero host cryptographic fallback: key generation, encapsulation, decryption, re-encryption, constant-time ciphertext comparison, and implicit rejection key selection are executed entirely within AIE2 tiles in local tile data memory (L1).

---

## 2. Mathematical & Algorithmic Parameters

| Parameter | ML-KEM-512 | ML-KEM-768 | ML-KEM-1024 |
|---|---|---|---|
| Matrix Dimension $k$ | 2 | 3 | 4 |
| Noise Parameter $\eta_1$ | 3 | 2 | 2 |
| Noise Parameter $\eta_2$ | 2 | 2 | 2 |
| Ciphertext Compression $d_u$ | 10 | 10 | 11 |
| Ciphertext Compression $d_v$ | 4 | 4 | 5 |
| Encapsulation Key $ek$ Size | 800 B | 1,184 B | 1,568 B |
| Decapsulation Key $dk$ Size | 1,632 B | 2,400 B | 3,168 B |
| Ciphertext $c$ Size | 768 B | 1,088 B | 1,568 B |
| Shared Key $K$ Size | 32 B | 32 B | 32 B |

---

## 3. Dataflow Microarchitecture

### 3.1 ML-KEM-768 Pipeline ($k=3$)

1. **KeyGen (5 Workers)**:
   - Worker 0: $G(d \parallel 3) \to (\rho, \sigma)$, sample $s_0..s_2$ ($\text{CBD}_2$), $e_0..e_2$ ($\text{CBD}_2$).
   - Worker 1: Row 0 expansion $\mathbf{A}[0, 0..2] \cdot \mathbf{s} + e_0 \to t_0$.
   - Worker 2: Row 1 expansion $\mathbf{A}[1, 0..2] \cdot \mathbf{s} + e_1 \to t_1$.
   - Worker 3: Row 2 expansion $\mathbf{A}[2, 0..2] \cdot \mathbf{s} + e_2 \to t_2$.
   - Worker 4: ByteEncode $ek[1184]$, $H(ek) = \text{SHA3-256}(ek)$, ByteEncode $dk[2400]$, CRC32 sealing.

2. **Encaps (5 Workers)**:
   - Worker 0: $H(ek) = \text{SHA3-256}(ek)$, $G(m \parallel H(ek)) \to (ar{K}, r)$, sample $y_0..y_2, e_{1,0}..e_{1,2}, e_2+\mu(m)$, decode $t_0..t_2$.
   - Worker 1: $\mathbf{A}^T[0, 0..2] \cdot \mathbf{y} + e_{1,0} \to \text{Compress}_{10}(u_0)$.
   - Worker 2: $\mathbf{A}^T[1, 0..2] \cdot \mathbf{y} + e_{1,1} \to \text{Compress}_{10}(u_1)$.
   - Worker 3: $\mathbf{A}^T[2, 0..2] \cdot \mathbf{y} + e_{1,2} \to \text{Compress}_{10}(u_2)$.
   - Worker 4: $\mathbf{t} \cdot \mathbf{y} + (e_2+\mu) \to \text{Compress}_4(v)$, assemble $c[1088] \parallel K[32]$, CRC32 sealing.

3. **Decaps (6 Workers)**:
   - Worker 0: $\text{K-PKE.Decrypt}(dk_{PKE}, c) \to m'$, forward $H(ek), z, \rho, c, \mathbf{t}$.
   - Worker 1: $G(m' \parallel H(ek)) \to (ar{K}', r')$, sample $y'_0..y'_2, e'_{1,0}..e'_{1,2}, e'_2+\mu(m')$.
   - Worker 2: $\mathbf{A}^T[0, 0..2] \cdot \mathbf{y}' + e'_{1,0} \to \text{Compress}_{10}(u'_0)$, compute $ar{K} = \text{SHAKE256}(z \parallel c, 32)$.
   - Worker 3: $\mathbf{A}^T[1, 0..2] \cdot \mathbf{y}' + e'_{1,1} \to \text{Compress}_{10}(u'_1)$.
   - Worker 4: $\mathbf{A}^T[2, 0..2] \cdot \mathbf{y}' + e'_{1,2} \to \text{Compress}_{10}(u'_2)$.
   - Worker 5: Re-encrypt $v'$, constant-time compare $c \oplus c'$, constant-time select $K = (c == c') ? ar{K}' : ar{K}$, CRC32 sealing.

---

### 3.2 ML-KEM-1024 Pipeline ($k=4$)

1. **KeyGen (6 Workers)**:
   - Worker 0: $G(d \parallel 4) \to (\rho, \sigma)$, sample $s_0..s_3$ ($\text{CBD}_2$), $e_0..e_3$ ($\text{CBD}_2$).
   - Workers 1–4: Rows 0..3 expansion $\mathbf{A}[i, 0..3] \cdot \mathbf{s} + e_i \to t_i$.
   - Worker 5: ByteEncode $ek[1568]$, $H(ek) = \text{SHA3-256}(ek)$, ByteEncode $dk[3168]$, CRC32 sealing.

2. **Encaps (6 Workers)**:
   - Worker 0: $H(ek) = \text{SHA3-256}(ek)$, $G(m \parallel H(ek)) \to (ar{K}, r)$, sample $y_0..y_3, e_{1,0}..e_{1,3}, e_2+\mu(m)$, decode $t_0..t_3$.
   - Workers 1–4: Rows 0..3 $\mathbf{A}^T[i, 0..3] \cdot \mathbf{y} + e_{1,i} \to \text{Compress}_{11}(u_i)$ (352 B each).
   - Worker 5: $\mathbf{t} \cdot \mathbf{y} + (e_2+\mu) \to \text{Compress}_5(v)$ (160 B), assemble $c[1568] \parallel K[32]$, CRC32 sealing.

3. **Decaps (7 Workers)**:
   - Worker 0: $\text{K-PKE.Decrypt}(dk_{PKE}, c) \to m'$, forward $H(ek), z, \rho, c, \mathbf{t}$.
   - Worker 1: $G(m' \parallel H(ek)) \to (ar{K}', r')$, sample $y'_0..y'_3, e'_{1,0}..e'_{1,3}, e'_2+\mu(m')$.
   - Worker 2: $\mathbf{A}^T[0, 0..3] \cdot \mathbf{y}' + e'_{1,0} \to \text{Compress}_{11}(u'_0)$, compute $ar{K} = \text{SHAKE256}(z \parallel c, 32)$.
   - Workers 3–5: Rows 1..3 $\mathbf{A}^T[i, 0..3] \cdot \mathbf{y}' + e'_{1,i} \to \text{Compress}_{11}(u'_i)$.
   - Worker 6: Re-encrypt $v'$, constant-time compare $c \oplus c'$, constant-time select $K = (c == c') ? ar{K}' : ar{K}$, CRC32 sealing.

---

## 4. Hardware Resource Compliance

All 35 AIE2 kernels across ML-KEM-512, ML-KEM-768, and ML-KEM-1024 strictly observe all hardware constraints:
1. **Instruction Memory**: Every kernel ELF is compiled and linked under the **16 KiB (16,384 B)** program memory limit per AIE2 tile.
2. **Tile Local Memory (L1)**: Ingress, internal ObjectFIFOs, and temporary buffers fit within 32 KiB local data memory.
3. **Worker Stack Allocation**: Explicit `stack_size=0x2000` (8,192 B) configuration with strictly scoped `{}` temporary variable lifetimes.
4. **Dataflow ObjectFIFOs**: Double-buffered stream ping-pong between tiles with zero intermediate host round-trips.
