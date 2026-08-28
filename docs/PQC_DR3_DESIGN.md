# Milestone DR3: Complete ML-KEM-512 `K-PKE.Encrypt` on AMD Phoenix NPU

## 1. Executive Summary

Milestone **DR3** achieves **100% on-device residency** for the complete post-quantum public-key encryption primitive ($\text{ML-KEM-512 } \text{K-PKE.Encrypt}$, FIPS 203 Algorithm 13) on AMD Phoenix NPU silicon (XDNA1 / AIE2).

Unlike hybrid or host-assisted implementations, the entire multi-stage encryption pipeline—including rejection sampling matrix expansion ($\text{SampleNTT}$), noise sampling ($\text{CBD}_3, \text{CBD}_2$), forward and inverse number-theoretic transforms ($\text{NTT}, \text{INTT}$), pointwise vector-matrix products in $\mathbb{Z}_q[X]/(X^{256}+1)$, polynomial modulus reductions, message encoding ($\text{Decompress}_1$), coefficient bit-packing ($\text{Compress}_{10}, \text{Compress}_4$), and output CRC32 validation—executes **strictly within tile-local data memories across the 5-tile NPU compute array**.

Zero host cryptographic fallback, zero intermediate DMA roundtrips, and zero runtime repairs are performed. The host only initiates two ingress DMAs (`descriptor[16]`, `request[864]`) and drains one egress DMA (`result[788]`).

---

## 2. Mathematical Specification (FIPS 203 Algorithm 13)

Given encryption key $ek = (\text{ByteEncode}_{12}(\hat{\mathbf{t}}) \parallel \rho) \in \mathbb{B}^{800}$, plaintext message $m \in \mathbb{B}^{32}$, and randomness $r \in \mathbb{B}^{32}$:

### Step 1: Noise Generation
$$
\mathbf{r} = \begin{pmatrix} \text{CBD}_3(\text{PRF}_\eta(r, 0)) \\ \text{CBD}_3(\text{PRF}_\eta(r, 1)) \end{pmatrix} \in R_q^2
$$

$$
\mathbf{e}_1 = \begin{pmatrix} \text{CBD}_2(\text{PRF}_\eta(r, 2)) \\ \text{CBD}_2(\text{PRF}_\eta(r, 3)) \end{pmatrix} \in R_q^2
$$

$$
e_2 = \text{CBD}_2(\text{PRF}_\eta(r, 4)) \in R_q
$$

### Step 2: Transform to NTT Domain
$$
\hat{\mathbf{r}} = \text{NTT}(\mathbf{r})
$$

### Step 3: Public Matrix Expansion
$$
\hat{\mathbf{A}}^T = \begin{pmatrix} \text{SampleNTT}(\rho \parallel 0 \parallel 0) & \text{SampleNTT}(\rho \parallel 0 \parallel 1) \\ \text{SampleNTT}(\rho \parallel 1 \parallel 0) & \text{SampleNTT}(\rho \parallel 1 \parallel 1) \end{pmatrix}
$$

### Step 4: Vector Polynomial Computations
$$
\mathbf{u} = \text{INTT}(\hat{\mathbf{A}}^T \circ \hat{\mathbf{r}}) + \mathbf{e}_1 \in R_q^2
$$

$$
v = \text{INTT}(\hat{\mathbf{t}}^T \circ \hat{\mathbf{r}}) + e_2 + \text{Decompress}_1(m) \in R_q
$$

### Step 5: Ciphertext Serialization
$$
c_1 = \text{ByteEncode}_{10}(\text{Compress}_{10}(\mathbf{u})) \in \mathbb{B}^{640}
$$

$$
c_2 = \text{ByteEncode}_4(\text{Compress}_4(v)) \in \mathbb{B}^{128}
$$

$$
c = c_1 \parallel c_2 \in \mathbb{B}^{768}
$$

---

## 3. Distributed 5-Tile Hardware Architecture

DR3 partitions the encryption pipeline across a 5-tile AIE2 compute array connected via memory-mapped ObjectFIFOs:

```
[Host DMA] -> (req[864], desc[16])
                  |
                  v
         +-----------------+
         | Tile 0: Worker 0 |  dr3_noise (Decodes t_hat, PRF CBD3/CBD2, NTT(r), e2+mu)
         +-----------------+
                  | Noise Token (3632 B)
                  v
         +-----------------+
         | Tile 1: Worker 1 |  dr3_col0_expand (SampleNTT A^T[0,0], A^T[0,1])
         +-----------------+
                  | Col0 Token (4656 B)
                  v
         +-----------------+
         | Tile 2: Worker 2 |  dr3_u0_acc (A^T[0]*r, INTT, +e1_0, Compress10 c1_0)
         +-----------------+
                  | U0 Token (3440 B)
                  v
         +-----------------+
         | Tile 3: Worker 3 |  dr3_col1_expand (SampleNTT A^T[1,0], A^T[1,1])
         +-----------------+
                  | Col1 Token (4464 B)
                  v
         +-----------------+
         | Tile 4: Worker 4 |  dr3_u1_v_serialize (A^T[1]*r, t^T*r, INTT, Compress, CRC32)
         +-----------------+
                  |
                  v Result Token (788 B)
             [Host DMA]
```

---

## 4. Key Microarchitectural Invariants & Solutions

### 4.1 Peano TableGen Immediate Mask Miscompilation
* **Phenomenon**: On AIE2, expressions of the form `x & 0xFFFFu` or `x & 0x3FFu` combined with Barrett reductions were lowered by Peano Clang++ into `and r, r, #0xfe81` (masking with 65153 instead of 65535), corrupting bit patterns.
* **Resolution**: Derived and verified exact 32-bit linear closed-form formulas with zero division and zero 64-bit intermediate products:

$$
\text{Compress}_4(x) = ((x \cdot 315 + 32701) \gg 16) \land \text{0x0F}
$$

$$
\text{Compress}_{10}(x) = ((x \cdot 161271 + 261911) \gg 19) \land \text{0x3FF}
$$

Both formulas are mathematically proven and verified on physical hardware to yield 100% bit-exact results for all $x \in [0, 3328]$.

### 4.2 AIE2 `lda.u16` Index-Doubling Hazard
* **Phenomenon**: Peano Clang++ emitted `lda.u16 r, [p, dj0]` with `dj0` set to byte offset $2k$. However, the AIE2 scalar execution unit treats `dj` in `lda.u16` as a half-word index, effectively accessing byte $2 \times (2k) = 4k$, causing off-by-factor-of-two memory corruptions.
* **Resolution**: Aligned all constant lookup tables (such as `kZetas`) to 32-bit words (`constexpr uint32_t kZetas[128]`), forcing the compiler to emit standard word loads `lda r, [p, dj0]`.

### 4.3 Pointer Strength Reduction Loop Bug
* **Phenomenon**: When `INTT` loops were written with dynamic strides `2u << stage`, LLVM's Loop Strength Reduction (LSR) pass reused the base pointer `p0 + j*4` without adding the stage stride `length*4`, loading identical values for both butterfly operands.
* **Resolution**: Implemented template-specialized static unrolling (`intt_stage<Len>` for $\text{Len} \in \{2, 4, 8, 16, 32, 64, 128\}$). Compile-time constant lengths generate deterministic post-increment pointer walks with zero displacement hazards.

---

## 5. Verification Summary

* **NIST ACVP Coverage**: 25/25 test vectors from the official NIST ACVP ML-KEM-512 suite.
* **Silicon Validation**: 100% bit-exact across all 25 vectors on AMD Ryzen 9 7940HS NPU.
* **Host DMA Overhead**: Exactly 2 ingress DMA pushes and 1 egress DMA pull per encryption operation.
