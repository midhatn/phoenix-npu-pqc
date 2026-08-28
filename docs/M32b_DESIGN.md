# M32b — Post-Quantum Cryptography: NTT-Domain Arithmetic on AIE2

## 1. Purpose

M32b delivers the NTT arithmetic layer of the Track 4 Post-Quantum Cryptography stack on the AMD Phoenix NPU. It implements FIPS 203 (ML-KEM) [Algorithms 9–12](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) — forward NTT, inverse NTT, `MultiplyNTTs`, `BaseCaseMultiply` — plus the polynomial vector-add and vector-sub primitives that every step of ML-KEM K-PKE, KeyGen, Encaps, and Decaps calls. Together with M32c (SHA-3 / SHAKE / SampleNTT / SamplePolyCBD), M32b closes the compute floor for on-tile ML-KEM.

## 2. Mathematical background

ML-KEM works in the ring $R_q = \mathbb{Z}_q[X]/(X^{256} + 1)$ with $q = 3329$ and $n = 256$, as specified in [FIPS 203 §2.4.4](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf). Since $q - 1 = 2^8 \cdot 13$, the base field contains primitive 256th roots of unity but not primitive 512th roots — the defining polynomial $X^{256}+1$ therefore factors modulo $q$ into **128 quadratic factors** rather than 256 linear factors ([CRYSTALS-Kyber round-3 specification, §1.4](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf)):

$$X^{256}+1 \;\equiv\; \prod_{i=0}^{127}\bigl(X^2 - \zeta^{2\mathrm{brv}_7(i)+1}\bigr) \pmod{q},$$where$ \zeta = 17 $is the first primitive 256th root of unity mod$ q $, and $\mathrm{brv}_7$ is the 7-bit bit-reversal function ([Kyber CFRG draft rev 04](https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html)). The negacyclic NTT therefore maps a polynomial to a vector of 128 degree-1 polynomials indexed in bit-reversed order — this is the "incomplete" NTT convention adopted verbatim by FIPS 203 and by every mainstream ML-KEM implementation.

### 2.1 Forward NTT (Algorithm 9)

Cooley-Tukey butterflies, standard-order input, bit-reversed output. In the pq-crystals reference the outer loop halves `len` from 128 down to 2, and at each level a fresh twiddle `zetas[k++]` is applied ([`ref/ntt.c`](https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c)):

```c
for (len = 128; len >= 2; len >>= 1)
  for (start = 0; start < 256; start = j + len) {
    zeta = zetas[k++];
    for (j = start; j < start + len; j++) {
      t = fqmul(zeta, r[j + len]);
      r[j + len] = r[j] - t;
      r[j]       = r[j] + t;
    }
  }
```

The 128-entry `zetas` table stores `R * 17^{brv7(k)} mod q` in signed representation for `k = 0..127`, with `R = 2^{16}` — this is the Montgomery-domain form, so every `fqmul` produces a value already reduced by a single factor of $R^{-1}$.

### 2.2 Inverse NTT (Algorithm 10)

Gentleman-Sande butterflies, bit-reversed input, standard-order output, plus a trailing scale by `f = 1441 = R^2 / n mod q`. The composition folds the negacyclic $1/n$ factor with a Montgomery-to-Montgomery lift, so the net effect of `invntt_tomont(ntt(a))` is $a \cdot R \pmod q$ — an extra factor of $R$ that later Montgomery multiplications naturally consume.

### 2.3 Base-case multiply (Algorithm 12) and `MultiplyNTTs` (Algorithm 11)

Because the NTT factors $X^{256}+1$ into quadratic factors, each pointwise product is a polynomial multiplication modulo $X^2 - \gamma$ with $\gamma = \pm\zeta^{2\mathrm{brv}_7(k)+1}$:

$$(a_0 + a_1 X)(b_0 + b_1 X) \bmod (X^2 - \gamma) \;=\; (a_0 b_0 + \gamma a_1 b_1) + (a_0 b_1 + a_1 b_0)\,X.$$

`poly_basemul_montgomery` iterates over 64 index blocks; the +/- pairing captures the two conjugate roots per bit-reversal orbit.

### 2.4 Montgomery and Barrett reductions

* **Montgomery** ([`ref/reduce.c`](https://github.com/pq-crystals/kyber/blob/main/ref/reduce.c)): given `int32_t a` in the range $[-q\cdot 2^{15}, q\cdot 2^{15}-1]$, returns `int16_t` congruent to $a \cdot R^{-1} \pmod q$ using `QINV = q^{-1} mod 2^{16} = -3327` and `R = 2^{16}`.
* **Barrett**: keeps coefficients in the canonical signed window $(-\tfrac{q-1}{2}, \tfrac{q-1}{2}]$ using $v = \lfloor(2^{26} + q/2)/q\rfloor = 20159$.

Both are transliterated line-for-line into the AIE2 kernel and the Python host reference.

## 3. Kernel architecture

Single-tile AIE2 kernel `ntt` (see [`tests/m32_mlkem/ntt_kernel.cc`](../tests/m32_mlkem/ntt_kernel.cc)), 2 in-fifos + 1 out-fifo — identical DMA topology to the silicon-PASSed M32c kernel to avoid the DMA rework we saw during M27.

| Buffer | Type | Slots | Purpose |
|---|---|---|---|
| `in_a` | int16 | 768 | Up to 3 concatenated 256-coefficient polynomials |
| `in_ctrl` | int16 | 8 | `{mode, n_polys, pad0, ...}` |
| `out_c` | int16 | 768 | Result polynomial(s) |

### 3.1 Modes

| Mode | Value | Semantics |
|---|---|---|
| `MODE_NTT` | 0 | Forward NTT on `n_polys` × 256-coeff polynomials |
| `MODE_INTT` | 1 | Inverse NTT (incl. `tomont` fold) on `n_polys` polynomials |
| `MODE_BASEMUL` | 2 | `poly_basemul_montgomery(a, b)` — A occupies `in_a[0..256)`, B occupies `in_a[256..512)` |
| `MODE_POLY_ADD` | 3 | `barrett_reduce(a[i] + b[i])` for i = 0..255 |
| `MODE_POLY_SUB` | 4 | `barrett_reduce(a[i] − b[i])` for i = 0..255 |

### 3.2 Style rules (M22..M32c lineage)

* `NOCPP`, no libc `<math.h>`.
* Every counted loop carries `#pragma clang loop unroll(disable)` to keep the on-tile program-memory budget under 16 KiB (M27 lesson).
* `ntt_forward` / `ntt_inverse` are `__attribute__((noinline))`, since they are called from multiple dispatch paths.
* The 128-entry `ZETAS` table lives in `.rodata` (256 bytes) and is verified byte-for-byte against an independent recomputation in the host reference.
* This document makes no constant-time or side-channel claim. In composed
  ML-KEM operations, NTT/INTT/base-multiply paths can process secret-derived
  polynomials; absence of intended secret-dependent control flow is not a
  side-channel evaluation.

## 4. Silicon-PASS gates

| Gate | Check |
|---|---|
| **(a) NTT / INTT round-trip** | Silicon `NTT` output bit-exact vs host reference on 3 random polynomials, and silicon `INTT(NTT(a))` bit-exact vs host reference AND satisfies the identity `INTT(NTT(a)) == R * a mod q`. |
| **(b) `MultiplyNTTs` vs schoolbook** | For 3 random polynomial pairs, silicon `INTT(NTT(a) o NTT(b))` matches a bigint negacyclic schoolbook `a * b mod (X²⁵⁶+1)` bit-exact. This closes the entire NTT → basemul → INTT chain against a purely mathematical ground truth that shares no code with the primary reference. |
| **(c) Zeta-table consistency** | Independent Python recompute of `R * 17^{brv7(k)} mod q` matches the 128-entry table embedded in the kernel byte-for-byte; silicon `NTT(δ_0)` and silicon `NTT(δ_2)` both match the host reference. δ₂ exercises non-trivial twiddles at every level, so any incorrect on-tile zeta value would diverge. |
| **(d) `poly_add` / `poly_sub`** | Silicon outputs bit-exact vs host reference on 3 random pairs, and the identity `add(a,b) + sub(a,b) == 2 a mod q` holds coefficient-wise on silicon. |

## 5. Host reference and transliteration cross-check

The Python host reference in [`tests/m32_mlkem/test_ntt_m32b.py`](../tests/m32_mlkem/test_ntt_m32b.py) is a line-for-line transliteration of `ntt_kernel.cc`, using explicit `int16` wrap semantics (`_to_int16`) to mirror the C code exactly.

The transliteration cross-check tool [`tools/m32b_kernel_transliteration_check.py`](../tools/m32b_kernel_transliteration_check.py) runs six independent audits against a second-source bigint-modular reference:

1. Independent 128-entry ZETAS recompute vs embedded table.
2. `schoolbook_negacyclic` (numpy int16, primary) vs `schoolbook_bigint` (unbounded Python ints).
3. Primary NTT → BASEMUL → INTT chain vs bigint schoolbook (end-to-end ML-KEM MultiplyNTTs oracle).
4. Primary `INTT(NTT(a)) == R * a mod q` on 3 polynomials.
5. Primary `poly_add` / `poly_sub` vs bigint modular reference.
6. Primary `basemul` replayed step-by-step in bigint Montgomery form.

Sandbox result: **17/17 PASS**.

## 6. Track 4 progress after M32b

| Milestone | Purpose | Status |
|---|---|---|
| M32c | SHA-3 / SHAKE + SampleNTT + SamplePolyCBD | historical physical record; current source revisions require separate evidence before inheriting status |
| **M32b** | NTT / INTT / MultiplyNTTs / BaseCaseMultiply + poly add/sub | **this milestone** |
| M32d | K-PKE component (FIPS 203 Alg 13–15) | next |
| M32e | ML-KEM-512 KeyGen / Encaps / Decaps (FIPS 203 Alg 19–21), bit-exact vs NIST example values | after |

## References

* NIST FIPS 203 (August 2024) — Module-Lattice-Based Key-Encapsulation Mechanism Standard. Algorithms 9–12, ring parameters n=256, q=3329, ζ=17. https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
* NIST FIPS 203 landing page. https://csrc.nist.gov/pubs/fips/203/final
* NIST Post-Quantum Cryptography project. https://csrc.nist.gov/projects/post-quantum-cryptography
* Avanzi R., Bos J., Ducas L., Kiltz E., Lepoint T., Lyubashevsky V., Schanck J. M., Schwabe P., Seiler G., Stehlé D. — CRYSTALS-Kyber Algorithm Specifications and Supporting Documentation (round-3 submission), 2021, §1.4 "The Number-Theoretic Transform". https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf
* pq-crystals/kyber reference implementation. `ref/ntt.c`, `ref/reduce.c`, `ref/poly.c`, `ref/params.h`. https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c
* pq-crystals/kyber reference implementation, `ref/reduce.c` (Montgomery and Barrett constants). https://github.com/pq-crystals/kyber/blob/main/ref/reduce.c
* pq-crystals/kyber reference implementation, `ref/poly.c` (`poly_basemul_montgomery`). https://github.com/pq-crystals/kyber/blob/main/ref/poly.c
* Schwabe P., Westerbaan B. — Kyber Post-Quantum KEM, Internet-Draft draft-cfrg-schwabe-kyber-04, September 2022. https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html
* Bos J. W., Renes J., van Vredendaal C. — Verified NTT Multiplications for NISTPQC Submission Kyber+SABER. IACR TCHES 2020, doi:10.13154/tches.v2020.i4.343-359. https://tches.iacr.org/index.php/TCHES/article/download/9838/9341/8389
* Higashi — A Gentle Introduction of NTT — Part III: The Kyber Trick. https://higashi.blog/2023/12/15/ntt-03/
* Naskrecki B. — Chapter 41: ML-KEM (Kyber) — Design and Implementation. https://bnaskrecki.faculty.wmi.amu.edu.pl/crypto/book/part14_lattice_crypto/ch41_ml_kem_kyber.html
* Dang Q. — FIPS 203 Update, NIST CSRC PQC 2024 talk. https://csrc.nist.gov/csrc/media/Presentations/2024/fips-203/images-media/dang-fips-203-pqc2024.pdf
* Shor P. W. — Algorithms for Quantum Computation: Discrete Logarithms and Factoring (1994). https://ieeexplore.ieee.org/document/365700
