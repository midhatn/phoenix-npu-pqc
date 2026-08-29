# DR5 Design: Device-Resident ML-KEM-512 `ML-KEM.KeyGen` on AMD Phoenix NPU

**Status:** Completed & Physically Validated on AMD Phoenix NPU Silicon (2026-08-28)  
**Standard:** NIST FIPS 203 (Module-Lattice-Based Key-Encapsulation Mechanism Standard), Algorithm 15  
**Hardware Target:** AMD Ryzen AI Phoenix NPU1 (Ryzen 9 7940HS / AIE2 4-Column Array)  
**Residency:** 100% Device-Resident (zero host CPU intermediate offload, zero fallback)

---

## 1. Executive Summary and Architectural Invariants

Milestone DR5 implements the complete, device-resident **ML-KEM-512 Key Generation** algorithm (`ML-KEM.KeyGen`) specified in **NIST FIPS 203 Algorithm 15**. 

The implementation satisfies the strict 100% NPU residency invariant:
1. **Public Ingress:** Exactly two host fills over DMA:
   - One 16-byte descriptor (`DESCRIPTOR_BYTES = 16`, Magic `0x00525101`).
   - One 64-byte request payload containing externally provided 32-byte seed $d$ and 32-byte seed $z$ ($d \parallel z$).
2. **On-Chip Seed Expansion:** Tile (0, 2) computes $G(d \parallel 2) = (\rho, \sigma)$ entirely on-device via SHA3-512 ($k = 2$ for ML-KEM-512). Neither $\rho$ nor $\sigma$ is derived on or transferred to the host CPU.
3. **On-Chip Matrix and Noise Generation:**
   - Worker W0 samples $\widehat{s}[0], \widehat{s}[1], \widehat{e}[0], \widehat{e}[1]$ via PRF $\text{SHAKE256}(\sigma, \text{nonce})$, $\text{CBD}_3$, and forward NTT.
   - Workers W1 and W3 expand the public matrix $\widehat{\mathbf{A}}[i,j]$ ($i, j \in \{0, 1\}$) on-chip via $\text{SampleNTT}(\text{SHAKE128}(\rho \parallel j \parallel i))$.
4. **On-Chip Accumulation:** Workers W2 and W4 compute the public polynomial vector $\widehat{\mathbf{t}} = \widehat{\mathbf{A}} \circ \widehat{\mathbf{s}} + \widehat{\mathbf{e}} \pmod{q}$ via dual-pair conjugate root Montgomery arithmetic.
5. **On-Chip Key Assembly & SHA3-256 Hashing:**
   - Worker W5 performs $\text{ByteEncode}_{12}(\widehat{\mathbf{t}})$ and concatenates $\rho$ to produce the encapsulation key $ek = \text{ByteEncode}_{12}(\widehat{\mathbf{t}}) \parallel \rho$ (800 bytes).
   - Worker W5 computes $H(ek) = \text{SHA3-256}(ek)$ (32 bytes) strictly within AIE tile memory.
   - Worker W5 encodes $dk_{PKE} = \text{ByteEncode}_{12}(\widehat{\mathbf{s}})$ (768 bytes) and packs the full decapsulation key:

$$
dk = dk_{PKE} \parallel ek \parallel H(ek) \parallel z \quad (1632\text{ bytes})
$$

6. **Terminal-Only Egress:** Only the final packed result record ($2452$ bytes: 20-byte header + 800-byte $ek$ + 1632-byte $dk$) transfers to the CPU after dispatch.

---

## 2. Mathematical Specification (FIPS 203 Algorithm 15)

The mathematical flow of `ML-KEM.KeyGen` is defined as:

$$
\begin{aligned}
(d, z) &\leftarrow \mathcal{B}^{32} \times \mathcal{B}^{32} \\
(ek_{PKE}, dk_{PKE}) &\leftarrow \text{K-PKE.KeyGen}(d) \\
ek &\leftarrow ek_{PKE} \\
dk &\leftarrow dk_{PKE} \parallel ek \parallel \text{SHA3-256}(ek) \parallel z \\
\text{return } &(ek, dk)
\end{aligned}
$$

Where:
- $ek_{PKE} = \text{ByteEncode}_{12}(\widehat{\mathbf{t}}) \parallel \rho$ (800 bytes)
- $dk_{PKE} = \text{ByteEncode}_{12}(\widehat{\mathbf{s}})$ (768 bytes)
- $H(ek) = \text{SHA3-256}(ek)$ (32 bytes)
- $z$ is the 32-byte implicit rejection seed retained for decapsulation failure handling.

---

## 3. AIE2 6-Worker Dataflow Architecture

The AIE2 dataflow graph executes across 6 tiles in the Phoenix NPU array connected via private ObjectFIFOs:

```
[Host DMA Ingress]
   | (64 B request: d[32] || z[32])
   | (16 B descriptor)
   v
[Tile 0: W0 Seed & Noise] ---> dr5_secret_token (2128 B)
                                 |
                                 v
[Tile 1: W1 Row 0 Expand] ---> dr5_row0_matrix (3152 B)
                                 |
                                 v
[Tile 2: W2 Row 0 Accum]  ---> dr5_row_state (2128 B)
                                 |
                                 v
[Tile 3: W3 Row 1 Expand] ---> dr5_row1_matrix (3152 B)
                                 |
                                 v
[Tile 4: W4 Row 1 Accum]  ---> dr5_final_token (2144 B)
                                 |
                                 v
[Tile 5: W5 Serialize Full] -> dr5_result (2452 B)
                                 |
                                 v
                       [Host DMA Egress]
```

### 3.1 Worker Roles and Execution Pipeline

1. **Worker W0 (`dr5_mlkem512_keygen_seed_noise.cc`)**:
   - Ingress: $d[32] \parallel z[32]$ (64 B) and descriptor (16 B).
   - Derives $(\rho, \sigma) = G(d \parallel 2)$ via SHA3-512 on-chip.
   - Preserves $z[32]$ in the secret token payload at offset $48$.
   - Generates $\widehat{s}[0], \widehat{s}[1], \widehat{e}[0], \widehat{e}[1]$ via $\text{SHAKE256}(\sigma, \text{nonce})$, $\text{CBD}_3$, and forward NTT.
   - Emits `dr5_secret_token` (2128 B).

2. **Worker W1 (`dr5_mlkem512_keygen_row0_expand.cc`)**:
   - Samples matrix polynomials $\widehat{\mathbf{A}}[0,0]$ and $\widehat{\mathbf{A}}[0,1]$ via $\text{SampleNTT}(\text{SHAKE128}(\rho \parallel j \parallel 0))$.
   - Emits `dr5_row0_matrix` (3152 B).

3. **Worker W2 (`dr5_mlkem512_keygen_row0_accumulate.cc`)**:
   - Computes $\widehat{t}_0 = \widehat{\mathbf{A}}[0,0] \circ \widehat{s}[0] + \widehat{\mathbf{A}}[0,1] \circ \widehat{s}[1] + \widehat{e}[0] \pmod{q}$.
   - Forwards secret state and carries forward $\widehat{e}[1]$ in `dr5_row_state` (2128 B).

4. **Worker W3 (`dr5_mlkem512_keygen_row1_expand.cc`)**:
   - Samples matrix polynomials $\widehat{\mathbf{A}}[1,0]$ and $\widehat{\mathbf{A}}[1,1]$ via $\text{SampleNTT}(\text{SHAKE128}(\rho \parallel j \parallel 1))$.
   - Emits `dr5_row1_matrix` (3152 B).

5. **Worker W4 (`dr5_mlkem512_keygen_row1_accumulate.cc`)**:
   - Computes $\widehat{t}_1 = \widehat{\mathbf{A}}[1,0] \circ \widehat{s}[0] + \widehat{\mathbf{A}}[1,1] \circ \widehat{s}[1] + \widehat{e}[1] \pmod{q}$.
   - Emits `dr5_final_token` (2144 B) containing $\rho$, $z$, $\widehat{s}[0]$, $\widehat{s}[1]$, $\widehat{t}[0]$, $\widehat{t}[1]$.

6. **Worker W5 (`dr5_mlkem512_keygen_serialize_full.cc`)**:
   - Encodes $ek = \text{ByteEncode}_{12}(\widehat{t}_0) \parallel \text{ByteEncode}_{12}(\widehat{t}_1) \parallel \rho$ (800 bytes).
   - Computes $H(ek) = \text{SHA3-256}(ek)$ on-chip (32 bytes) across 5 full 136-byte blocks + 1 partial 120-byte block.
   - Encodes $dk_{PKE} = \text{ByteEncode}_{12}(\widehat{s}_0) \parallel \text{ByteEncode}_{12}(\widehat{s}_1)$ (768 bytes).
   - Assembles $dk = dk_{PKE} \parallel ek \parallel H(ek) \parallel z$ (1632 bytes).
   - Calculates on-chip CRC32 checksum over the entire 2432-byte payload.
   - Emits terminal result record (2452 bytes).

---

## 4. On-Chip Memory Layouts and Offsets

```
SecretToken (2128 Bytes):
  [0x0000..0x000F] Header (Magic: 'SECT', request_id, status, pad) [16 B]
  [0x0010..0x002F] rho [32 B]
  [0x0030..0x004F] z [32 B]
  [0x0050..0x024F] s_hat0 [512 B]
  [0x0250..0x044F] s_hat1 [512 B]
  [0x0450..0x064F] e_hat0 [512 B]
  [0x0650..0x084F] e_hat1 [512 B]

MatrixToken (3152 Bytes):
  [0x0000..0x084F] SecretToken payload [2128 B]
  [0x0850..0x0A4F] A[row, 0] [512 B]
  [0x0A50..0x0C4F] A[row, 1] [512 B]

RowStateToken (2128 Bytes):
  [0x0000..0x004F] Header + rho + z [80 B]
  [0x0050..0x044F] s_hat0 + s_hat1 [1024 B]
  [0x0450..0x064F] t_hat0 [512 B]
  [0x0650..0x084F] e_hat1 [512 B]

FinalToken (2144 Bytes):
  [0x0000..0x004F] Header + rho + z [80 B]
  [0x0050..0x044F] s_hat0 + s_hat1 [1024 B]
  [0x0450..0x064F] t_hat0 [512 B]
  [0x0650..0x084F] t_hat1 [512 B]
  [0x0850..0x085F] Pad [16 B]

Result Record (2452 Bytes):
  [0x0000..0x0013] Header (Magic: 'MR5G', request_id, status, payload_len=2432, crc32) [20 B]
  [0x0014..0x0333] ek [800 B]
  [0x0334..0x0993] dk [1632 B]
```

---

## 5. Microarchitectural Verification

1. **SHA3-256 Multi-Block Squeeze on 800-byte Key:** Rate is 136 bytes. The 800-byte encapsulation key absorbs into 5 full blocks (680 bytes) and 1 partial block (120 bytes). Padding bytes are placed at offsets $120$ (`0x06`) and $135$ (`0x80`), followed by a single Keccak-f[1600] permutation.
2. **Dual-Pair Montgomery BaseMul Structure:** Polynomial arithmetic uses the conjugate twiddle root alternating pairs ($+\gamma$, $q - \gamma$) across 64 iterations, matching the standard FIPS 203 structure.
3. **32-Bit Scalar Word Access:** Coefficients are loaded and stored via 32-bit aligned accesses (`load_le16` byte assembly and `store_pair_word` 32-bit writes) avoiding AIE2 `lda.u16` index doubling hazards.

---

## 6. References

- [NIST FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [NIST FIPS 202: SHA-3 Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [PQC Roadmap](PQC_ROADMAP.md)
