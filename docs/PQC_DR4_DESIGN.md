# Milestone DR4: Complete ML-KEM-512 `K-PKE.Decrypt` on AMD Phoenix NPU

## 1. Executive Summary

Milestone **DR4** achieves **100% on-device residency** for the complete post-quantum public-key decryption primitive ($\text{ML-KEM-512 } \text{K-PKE.Decrypt}$, FIPS 203 Algorithm 14) on AMD Phoenix NPU silicon (XDNA1 / AIE2).

In DR4, the entire decryption pipeline—including 10-bit ciphertext decompression ($\text{Decompress}_{10}$), 4-bit ciphertext decompression ($\text{Decompress}_4$), 12-bit secret key decoding ($\text{ByteDecode}_{12}$), forward number-theoretic transforms ($\text{NTT}$), pointwise vector-polynomial inner products in NTT domain ($\text{MultiplyNTTs}$), inverse number-theoretic transform ($\text{INTT}$), modular error polynomial subtraction ($v - w_{\text{poly}} \pmod q$), 1-bit threshold message compression ($\text{Compress}_1$), and output CRC32 checksum validation—executes **strictly within tile-local data memories across the 2-tile NPU compute array**.

Zero host cryptographic fallback, zero intermediate DMA roundtrips, and zero runtime repairs are performed. The host only initiates two ingress DMAs (`descriptor[16]`, `request[1536]`) and drains one egress DMA (`result[52]`).

---

## 2. Mathematical Specification (FIPS 203 Algorithm 14)

Given private key $dk_{PKE} = \text{ByteEncode}_{12}(\hat{\mathbf{s}}) \in \mathbb{B}^{768}$ and ciphertext $c = c_1 \parallel c_2 \in \mathbb{B}^{768}$ ($c_1 \in \mathbb{B}^{640}, c_2 \in \mathbb{B}^{128}$):

### Step 1: Ciphertext Polynomial Decompression
$$
\mathbf{u}[0] = \text{Decompress}_{10}(\text{ByteDecode}_{10}(c_1[0:320])) \in R_q
$$

$$
\mathbf{u}[1] = \text{Decompress}_{10}(\text{ByteDecode}_{10}(c_1[320:640])) \in R_q
$$

$$
v = \text{Decompress}_4(\text{ByteDecode}_4(c_2[0:128])) \in R_q
$$

where the exact integer decompression formulas are:
$$
\text{Decompress}_{10}(y) = \lfloor (y \cdot 3329 + 512) \gg 10 \rfloor
$$

$$
\text{Decompress}_4(y) = \lfloor (y \cdot 3329 + 8) \gg 4 \rfloor
$$

### Step 2: Secret Key Vector Decoding
$$
\hat{\mathbf{s}}[0] = \text{ByteDecode}_{12}(dk_{PKE}[0:384]) \in R_q
$$

$$
\hat{\mathbf{s}}[1] = \text{ByteDecode}_{12}(dk_{PKE}[384:768]) \in R_q
$$

### Step 3: Forward NTT on Ciphertext Vector
$$
\hat{\mathbf{u}}[0] = \text{NTT}(\mathbf{u}[0]), \quad \hat{\mathbf{u}}[1] = \text{NTT}(\mathbf{u}[1])
$$

### Step 4: Pointwise Inner Product & Inverse NTT
For $i \in [0, 63]$ with $\gamma = \text{kZetas}[64 + i]$:
$$
(\hat{w}[4i], \hat{w}[4i+1]) = \text{BaseMul}(\hat{\mathbf{s}}_0[4i], \hat{\mathbf{s}}_0[4i+1], \hat{\mathbf{u}}_0[4i], \hat{\mathbf{u}}_0[4i+1], \gamma) + \text{BaseMul}(\hat{\mathbf{s}}_1[4i], \hat{\mathbf{s}}_1[4i+1], \hat{\mathbf{u}}_1[4i], \hat{\mathbf{u}}_1[4i+1], \gamma)
$$

$$
(\hat{w}[4i+2], \hat{w}[4i+3]) = \text{BaseMul}(\hat{\mathbf{s}}_0[4i+2], \hat{\mathbf{s}}_0[4i+3], \hat{\mathbf{u}}_0[4i+2], \hat{\mathbf{u}}_0[4i+3], q - \gamma) + \text{BaseMul}(\hat{\mathbf{s}}_1[4i+2], \hat{\mathbf{s}}_1[4i+3], \hat{\mathbf{u}}_1[4i+2], \hat{\mathbf{u}}_1[4i+3], q - \gamma)
$$

$$
w_{\text{poly}} = \text{INTT}(\hat{w}) \in R_q
$$

### Step 5: Polynomial Error Subtraction
$$
w[i] = (v[i] \ge w_{\text{poly}}[i]) ? (v[i] - w_{\text{poly}}[i]) : (v[i] + 3329 - w_{\text{poly}}[i])
$$

### Step 6: 1-Bit Message Compression & Serialization
$$
m = \text{ByteEncode}_1(\text{Compress}_1(w)) \in \mathbb{B}^{32}
$$

where $\text{Compress}_1(x) = (x \ge 833 \land x \le 2496) ? 1 : 0$.

---

## 3. Distributed 2-Tile Hardware Architecture

DR4 partitions the decryption pipeline across a 2-tile AIE2 compute array connected via memory-mapped ObjectFIFOs:

```
[Host Ingress DMA] -> (req[1536], desc[16])
                           |
                           v
                  +-----------------+
                  | Tile 0: Worker 0 |  dr4_decompress_ntt
                  +-----------------+  (Decode dk_PKE, Decompress u/v, NTT u0/u1)
                           |
                           | Decompress Token (5136 B)
                           v
                  +-----------------+
                  | Tile 1: Worker 1 |  dr4_accumulate_serialize
                  +-----------------+  (Inner Product, INTT, v - w, Compress1, CRC32)
                           |
                           v Result Token (52 B)
                      [Host Egress DMA]
```

---

## 4. Key Microarchitectural Invariants & Solutions

### 4.1 32-Bit Alignment for All Polynomial Intermediates
* **Phenomenon**: AIE2 scalar load `lda.u16 [p, dj0]` interprets dynamic index `dj0` as a half-word index, causing off-by-factor-of-two memory address calculations when loading from 16-bit arrays.
* **Resolution**: Stored all polynomial buffers in `DecompressToken` (`s_hat0`, `s_hat1`, `u_hat0`, `u_hat1`, `v`) as 32-bit `uint32_t` arrays, forcing standard 32-bit word loads `lda r, [p, dj0]`.

### 4.2 FIPS 203 Twiddle Conjugation in MultiplyNTTs
* **Phenomenon**: In ML-KEM degree-256 polynomials, the 128 degree-2 irreducible factors alternate roots: the first pair $(4i+0, 4i+1)$ multiplies with $+\gamma = \text{kZetas}[64+i]$, while the second pair $(4i+2, 4i+3)$ multiplies with the algebraic conjugate root $-\gamma \equiv q - \text{kZetas}[64+i] \pmod q$.
* **Resolution**: Implemented the dual-pair `BaseMul` structure spanning 64 iterations, matching FIPS 203 Definition 4.3 with 100% bit-exactness.

### 4.3 Template-Specialized Forward & Inverse NTT Unrolling
* **Phenomenon**: Dynamic stride outer loops triggered LLVM Loop Strength Reduction (LSR) pointer aliasing bugs.
* **Resolution**: Employed static template unrolling (`ntt_stage<Len>` and `intt_stage<Len>` for $\text{Len} \in \{2, 4, 8, 16, 32, 64, 128\}$) with `#pragma clang loop unroll(disable)` on inner scalar loops.

---

## 5. Verification Summary

* **NIST ACVP Coverage**: 25/25 test vectors from the official NIST ACVP ML-KEM-512 suite.
* **Silicon Validation**: 100% bit-exact across all 25 vectors on AMD Ryzen 9 7940HS NPU.
* **Host DMA Overhead**: Exactly 2 ingress DMA pushes (`desc[16]`, `req[1536]`) and 1 egress DMA pull (`result[52]`).
