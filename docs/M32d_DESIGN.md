# M32d — Post-Quantum Cryptography: K-PKE byte-serialization on AIE2

## 1. Purpose

M32d delivers the byte-level layer of the Track 4 Post-Quantum Cryptography stack on the AMD Phoenix NPU. It implements every Compress / Decompress and ByteEncode / ByteDecode routine that FIPS 203 [Algorithms 13–15 (K-PKE.KeyGen, K-PKE.Encrypt, K-PKE.Decrypt)](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) calls around every polynomial in ML-KEM:

- `Compress_d` / `Decompress_d` for $d \in \{4, 10\}$ (ciphertext compression at the ML-KEM-512 parameters)
- `ByteEncode_12` / `ByteDecode_12` (lossless serialization of coefficients in $\mathbb{Z}_q$)
- `poly_frommsg` / `poly_tomsg` (message ↔ polynomial with $d = 1$)

Combined with **M32b** (NTT / INTT / MultiplyNTTs / BaseCaseMultiply, poly add/sub) and **M32c** (SHA-3 / SHAKE / SampleNTT / SamplePolyCBD), M32d closes the compute floor needed to compose ML-KEM-512 KeyGen / Encaps / Decaps in **M32e**.

## 2. Mathematical background

### 2.1 Compress / Decompress

FIPS 203 §4.2.1 [equations (4.7)–(4.8)](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf):

$$
\mathrm{Compress}_d(x) = \left\lceil \frac{2^d}{q} \cdot x \right\rfloor \bmod 2^d, \qquad
\mathrm{Decompress}_d(y) = \left\lceil \frac{q}{2^d} \cdot y \right\rfloor,
$$with$ q = 3329 $, $n = 256$. $\mathrm{Compress}_d$ is lossy for $d < 12$; the standard notes that $\mathrm{Compress}_d(\mathrm{Decompress}_d(y)) = y$ for every $y \in \mathbb{Z}_{2^d}$ — decompression is a right inverse of compression, and that property lets ML-KEM tolerate the lossy compression baked into every ciphertext coefficient.

The pq-crystals reference computes both rounds with magic-constant multiply-and-shift sequences (avoiding integer division). For $d = 4$, [ref/poly.c poly_compress](https://github.com/pq-crystals/kyber/blob/main/ref/poly.c):

```c
d0 = u << 4;
d0 += 1665;
d0 *= 80635;
d0 >>= 28;
t[j] = d0 & 0xf;
```

For $d = 10$, [ref/polyvec.c polyvec_compress](https://github.com/pq-crystals/kyber/blob/main/ref/polyvec.c):

```c
d0 = t[k];
d0 <<= 10;
d0 += 1665;
d0 *= 1290167;
d0 >>= 32;
t[k] = d0 & 0x3ff;
```

Both sequences are chosen so that for every input in $[0, q-1]$ they yield the same result as $\lceil (2^d / q) \cdot x \rfloor \bmod 2^d$ with round-half-up semantics. The existing five-trial comparison is only a smoke check; an equivalence claim requires an exhaustive-domain test or a proof.

### 2.2 ByteEncode_d / ByteDecode_d

FIPS 203 §4.2.1 defines `ByteEncode_d(F)` as writing the integer coefficients of $F$ as $d$-bit little-endian chunks and packing them into a byte array of length $32d$. `ByteDecode_d` is the inverse. For $d = 12$ the encoding is lossless for canonical ML-KEM coefficients because $q=3329 < 2^{12}$and$\lceil \log_2 q \rceil = 12$; for $d < 12$ the encoding assumes each coefficient already fits in $d$ bits (which the caller ensures via `Compress`).

The pq-crystals kernel handles two special cases inline:

- `poly_tobytes` / `poly_frombytes` — $d = 12$, 3 bytes per pair of coefficients.
- `poly_frommsg` / `poly_tomsg` — $d = 1$, 1 byte per 8 coefficients, with the message-bit → coefficient mapping $b \mapsto b \cdot \lceil q/2 \rceil = b \cdot 1665$.

### 2.3 ML-KEM-512 parameter contract

[FIPS 203 Table 2](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) fixes the ML-KEM-512 parameters as $k = 2$, $\eta_1 = 3$, $\eta_2 = 2$, $d_u = 10$, $d_v = 4$. Every M32d mode targets exactly the $d$ values ML-KEM-512 needs:

| Purpose | $d$ | Bytes / poly |
|---|---|---|
| ciphertext `v` compression | 4 | 128 |
| ciphertext `u` compression (per-poly slice) | 10 | 320 |
| public key `t_hat` serialization | 12 | 384 |
| message m ↔ poly | 1 | 32 |

## 3. Kernel architecture

Single-tile AIE2 kernel `kpke` (see [`tests/m32_mlkem/kpke_kernel.cc`](../tests/m32_mlkem/kpke_kernel.cc)), 2 in-fifos + 1 out-fifo — identical DMA topology to the silicon-PASSed M32c and M32b kernels.

| Buffer | Type | Lanes | Purpose |
|---|---|---|---|
| `in_a` | int16 | 512 | Input polynomial (up to 256 int16 coefficients) OR packed byte stream (up to 384 bytes, one byte per lane low-order) |
| `in_ctrl` | int16 | 8 | `{mode, ...}` |
| `out_c` | int16 | 512 | Output — opposite type of `in_a` |

Byte streams are carried in the low byte of int16 lanes with the high byte cleared — the M32c pattern which silicon-PASSed. Sender and receiver both agree on the width.

### 3.1 Modes

| Mode | Value | Semantics | In | Out |
|---|---|---|---|---|
| `MODE_COMPRESS_D4` | 0 | `poly_compress d=4` | 256 int16 | 128 bytes |
| `MODE_DECOMPRESS_D4` | 1 | `poly_decompress d=4` | 128 bytes | 256 int16 |
| `MODE_COMPRESS_D10` | 2 | `polyvec_compress` (per-poly slice) | 256 int16 | 320 bytes |
| `MODE_DECOMPRESS_D10` | 3 | `polyvec_decompress` (per-poly slice) | 320 bytes | 256 int16 |
| `MODE_TOBYTES_D12` | 4 | `poly_tobytes` | 256 int16 | 384 bytes |
| `MODE_FROMBYTES_D12` | 5 | `poly_frombytes` | 384 bytes | 256 int16 |
| `MODE_FROMMSG` | 6 | `poly_frommsg` | 32 bytes | 256 int16 |
| `MODE_TOMSG` | 7 | `poly_tomsg` | 256 int16 | 32 bytes |

### 3.2 Style rules (M22..M32b lineage)

- `NOCPP`, no libc `<math.h>`.
- Every counted loop carries `#pragma clang loop unroll(disable)` to keep the on-tile program-memory budget under 16 KiB (M27 lesson).
- All static helpers are `__attribute__((noinline))`.
- The output buffer is zeroed at entry so unused tail lanes are deterministic.
- Multiplier constants (`1665`, `80635`, `1290167`, `645084`, ...) are quoted verbatim from pq-crystals `ref/poly.c` and `ref/polyvec.c` — never recomputed.

### 3.3 Timing side-channel note

`poly_frommsg` uses a constant-time-style bit-mask multiplication (`bit * mask`) rather than `cmov_int16`, since AIE2 has no cmov intrinsic. This document makes no constant-time or side-channel claim: byte decoding and composed K-PKE operations can process secret-key-derived, noise-derived, or plaintext-derived values. Absence of intended secret-dependent control flow is not a side-channel evaluation.

## 4. Silicon-PASS gates

| Gate | Check |
|---|---|
| **(a) Compress / Decompress d=4** | Silicon `Compress_d4` and `Decompress_d4` bit-exact vs the line-for-line host reference on 3 random polynomials each; on-silicon round-trip `Compress_d4(Decompress_d4(y)) == y` for random uint4 lattice inputs. |
| **(b) Compress / Decompress d=10** | Same as (a) but for the $d_u = 10$ ciphertext compression, with 320-byte payloads and 10-bit codewords. |
| **(c) ByteEncode / ByteDecode d=12** | Silicon `poly_tobytes` / `poly_frombytes` bit-exact vs host on 3 random polynomials; on-silicon round-trip `frombytes_d12(tobytes_d12(a)) == canonical(a) mod 2^12` — this catches any packing / unpacking bit-order error. |
| **(d) Message ↔ poly (d=1)** | Silicon `poly_frommsg` bit-exact vs host on 3 random 32-byte messages; on-silicon `tomsg(frommsg(m)) == m` — verifies that both directions correctly handle the $b \cdot \lceil q/2 \rceil$ mapping and the compress-back-to-1-bit rounding on the return leg. |

## 5. Host reference and transliteration cross-check

The Python host reference in [`tests/m32_mlkem/test_kpke_m32d.py`](../tests/m32_mlkem/test_kpke_m32d.py) is a line-for-line transliteration of `kpke_kernel.cc` — same magic constants, same bit-shifts, same overflow windows (via explicit `_U32`, `_U64` masks).

The transliteration cross-check tool [`tools/m32d_kernel_transliteration_check.py`](../tools/m32d_kernel_transliteration_check.py) audits the primary against an independent implementation that uses **exact rational rounding**:

$$\mathrm{Compress}_d(x) = \left\lfloor \frac{2^d \cdot x + \lfloor q/2 \rfloor}{q} \right\rfloor \bmod 2^d,$$

computed with Python's unbounded integers. That formulation shares zero code with the pq-crystals magic-constant fast path — every match confirms the primary implementation is bit-exact against the mathematical definition, not just against itself.

Six checks:

1. `_canonical` primary vs bigint modular over the full `[-q, q)` range.
2. `compress_d4` / `decompress_d4` primary vs bigint-rational — 5/5 each.
3. `compress_d10` / `decompress_d10` primary vs bigint-rational — 5/5 each.
4. `tobytes_d12` / `frombytes_d12` primary vs independent byte-packing — 5/5 each.
5. `frommsg` / `tomsg` primary vs independent — 5/5 each.
6. Primary end-to-end algebraic identities:
   - `Compress_d4(Decompress_d4(y)) == y` — 5 trials
   - `Compress_d10(Decompress_d10(y)) == y` — 5 trials
   - `frombytes_d12(tobytes_d12(a)) == canonical(a) mod 2^12` — 5 trials
   - `tomsg(frommsg(m)) == m` — 5 trials

**Sandbox result: 6/6 PASS.**

## 6. Track 4 progress after M32d

| Milestone | Purpose | Status |
|---|---|---|
| M32c | SHA-3 / SHAKE + SampleNTT + SamplePolyCBD | historical physical result; current source revision requires separate evidence before inheriting that status |
| M32b | NTT / INTT / MultiplyNTTs / BaseCaseMultiply + poly add / sub | silicon PASS |
| **M32d** | K-PKE byte-serialization (Compress / Decompress / ByteEncode / ByteDecode) | **this milestone** |
| M32e | ML-KEM-512 KeyGen / Encaps / Decaps (FIPS 203 Algs 19–21), bit-exact vs NIST example values | next |

## References

- NIST FIPS 203 (August 2024) — Module-Lattice-Based Key-Encapsulation Mechanism Standard. Algorithms 13–15 (K-PKE.KeyGen / Encrypt / Decrypt), Section 4.2.1 (Compress / Decompress / ByteEncode / ByteDecode), Table 2 (ML-KEM-512 parameters $k=2$, $d_u = 10$, $d_v = 4$). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 203 landing page. https://csrc.nist.gov/pubs/fips/203/final
- NIST Post-Quantum Cryptography project. https://csrc.nist.gov/projects/post-quantum-cryptography
- Avanzi R., Bos J., Ducas L., Kiltz E., Lepoint T., Lyubashevsky V., Schanck J. M., Schwabe P., Seiler G., Stehlé D. — CRYSTALS-Kyber Algorithm Specifications and Supporting Documentation (round-3 submission), 2021. https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf
- pq-crystals/kyber reference implementation, `ref/poly.c` — `poly_compress`, `poly_decompress`, `poly_tobytes`, `poly_frombytes`, `poly_frommsg`, `poly_tomsg`. https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
- pq-crystals/kyber reference implementation, `ref/polyvec.c` — `polyvec_compress`, `polyvec_decompress`. https://github.com/pq-crystals/kyber/blob/main/ref/polyvec.c
- pq-crystals/kyber reference implementation, `ref/params.h` — `KYBER_POLYCOMPRESSEDBYTES = 128`, `KYBER_POLYVECCOMPRESSEDBYTES = 320 * KYBER_K`, `KYBER_POLYBYTES = 384`, `KYBER_ETA1 = 3`, `KYBER_ETA2 = 2`. https://github.com/pq-crystals/kyber/blob/main/ref/params.h
- Schwabe P., Westerbaan B. — Kyber Post-Quantum KEM, Internet-Draft draft-cfrg-schwabe-kyber-04, September 2022. https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html
- CRYPTREC — ML-KEM Evaluation Report, 2025 (parameter table with $d_u = 10$, $d_v = 4$ for ML-KEM-512). https://pqshield.com/wp-content/uploads/2026/03/cryptrec-ex-3502-2025.pdf
- Isohanni J. — CRYSTALS-Kyber Compression and KEM (parameter tables, compression semantics). https://jani.isohanni.fi/crystals-kyber-compression-and-kem/
- Dang Q. — FIPS 203 Update, NIST CSRC PQC 2024. https://csrc.nist.gov/csrc/media/Presentations/2024/fips-203/images-media/dang-fips-203-pqc2024.pdf
