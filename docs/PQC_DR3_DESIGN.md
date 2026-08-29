# Milestone DR3: ML-KEM-512 K-PKE Encrypt Device-Residency Architecture

## 1. Scope and Cryptographic Boundary

Milestone DR3 implements the complete, device-resident `K-PKE.Encrypt` operation on the AMD Phoenix NPU (XDNA1/AIE2) architecture. All mathematical operations—encryption noise sampling ($CBD_3$, $CBD_2$), NTT transforms, public matrix polynomial multiplication and accumulation, polynomial addition, inverse NTT, polynomial compression, and byte serialization—execute 100% on-device across the 4-worker AIE2 compute array.

---

## 2. Mathematical Specification (FIPS 203 Section 5.2 / Algorithm 14)

### Step 1: Pseudorandom Noise Vector Sampling

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

## 3. AIE2 Hardware Pipeline Mapping

```
[Host DMA Ingress] (832 bytes: ek=800B, m=32B, r=32B)
       │
       ▼
 ┌───────────────┐
 │ Worker 0 (W0) │  --> PRF & CBD Noise Sampling (r[0], r[1], e1[0], e1[1], e2)
 └───────┬───────┘
         │ ObjectFIFO (256-lane vectors)
         ▼
 ┌───────────────┐
 │ Worker 1 (W1) │  --> Forward NTT: r_hat = NTT(r)
 └───────┬───────┘
         │ ObjectFIFO
         ▼
 ┌───────────────┐
 │ Worker 2 (W2) │  --> Matrix Expansion & PolyMul Accumulation: u_hat = A^T * r_hat, v_hat = t_hat^T * r_hat
 └───────┬───────┘
         │ ObjectFIFO
         ▼
 ┌───────────────┐
 │ Worker 3 (W3) │  --> INTT, Decompress(m), Add Noise, Compress & ByteEncode Serialization
 └───────┬───────┘
         │
         ▼
[Host DMA Egress] (788 bytes: Status Envelope + 768-byte Ciphertext c)
```

---

## 4. Barrett & Fast Compression Arithmetic

For coefficient compression without hardware integer division on AIE2:

$$
\text{Compress}_4(x) = ((x \cdot 315 + 32701) \gg 16) \land \text{0x0F}
$$

$$
\text{Compress}_{10}(x) = ((x \cdot 161271 + 261911) \gg 19) \land \text{0x3FF}
$$

Both formulas are mathematically proven and verified on physical hardware to yield 100% bit-exact results for all $x \in [0, 3328]$.
