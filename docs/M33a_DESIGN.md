# M33a — Dilithium NTT / INTT / BASEMUL / REDUCE (FIPS 204 ML-DSA)

Post-Quantum Cryptography — FIPS 204 (ML-DSA) primitive layer, silicon-side.
This milestone lands the number-theoretic transform hardware for ML-DSA-44 /
ML-DSA-65 / ML-DSA-87 on the Phoenix NPU. All three ML-DSA parameter sets use
the **same** ring and thus the same NTT kernel — parameter-set differences
(k, l, eta, tau, gamma_1) live in the composer, not the primitive.

## Scope

- One AIE2 kernel `tests/m33_mldsa/dilithium_ntt_kernel.cc` with four modes:

  | mode | operation                                                       | in_a         | in_b        | out_c                             |
  |-----:|-----------------------------------------------------------------|:-------------|:------------|:----------------------------------|
  | 0    | forward NTT, in-place, bit-reversed output                      | 256 × int32  | —           | 256 × int32                       |
  | 1    | inverse NTT + multiply by F, standard-order output              | 256 × int32  | —           | 256 × int32                       |
  | 2    | pointwise Montgomery basemul `(a · b · R⁻¹) mod q`              | 256 × int32  | 256 × int32 | 256 × int32                       |
  | 3    | reduce `a → t ∈ (−q/2, q/2]` (Barrett-style)                    | 256 × int32  | —           | 256 × int32                       |

- Host test `tests/m33_mldsa/test_dilithium_ntt_m33a.py` gates all four modes
  against `dilithium-py v1.4.0` and against a schoolbook negacyclic multiplier
  on the end-to-end round trip.

- Transliteration cross-check `tools/m33a_kernel_transliteration_check.py`
  re-derives Q, QINV, MONT_R_MOD, F_MONT, and the ZETAS_MONT[256] table from
  first principles and diffs the parsed C source.

## Ring and constants (FIPS 204 § 2.4, § 4)

- Modulus: `q = 8380417` (a 23-bit prime, `q = 2²³ − 2¹³ + 1`).
- Degree: `n = 256`.
- Ring: `R_q = ℤ_q[X] / (X²⁵⁶ + 1)`.
- Primitive 512-th root of unity: `ζ = 1753`.
- ZETAS in bit-reversed order (`ζ_k = ζ^{br₈(k)}`), pre-scaled by `R = 2³²`
  and stored as signed int32 in `(−q, q)`.

All three ML-DSA parameter sets (44, 65, 87) share the same ring — the primitive
layer needs to be built once. `k` and `l` (module dimensions) only affect how
many independent 256-poly NTTs the composer requests per KeyGen / Sign / Verify.

| Param set   | k | l | η | τ  | γ₁      | γ₂       | ω  | c̃ bytes |
|:------------|--:|--:|--:|---:|--------:|---------:|---:|--------:|
| ML-DSA-44   | 4 | 4 | 2 | 39 | 2¹⁷     | (q−1)/88 | 80 | 32      |
| ML-DSA-65   | 6 | 5 | 4 | 49 | 2¹⁹     | (q−1)/32 | 55 | 48      |
| ML-DSA-87   | 8 | 7 | 2 | 60 | 2¹⁹     | (q−1)/32 | 75 | 64      |

## Montgomery reduction (32-bit)

Ref-C dilithium chooses `R = 2³²`. With this choice:

- `QINV = 58728449` such that `Q · QINV ≡ 1 (mod 2³²)`.
- `R mod Q = 4193792`.
- For inverse NTT the standard `n⁻¹` factor is folded into a single Montgomery
  constant `F_MONT = (R² · n⁻¹) mod Q = 41978` (signed). Applying `F_MONT` via
  Montgomery reduction at the end of `invntt` strips one factor of R.

The `mont_reduce(a: int64) -> int32` primitive returns a representative in
`(−q, q)` congruent to `a · R⁻¹ (mod q)`:

```c
int32_t t = (int32_t)(a * QINV);      // low 32 bits, signed
return (a - (int64_t)t * Q) >> 32;    // arithmetic shift
```

## Butterfly semantics vs plain modular arithmetic

The ZETAS table is pre-scaled by R, so each butterfly is

    t = mont_reduce(ζ_R · c[j+len]) = ζ · c[j+len]  (mod q).

Consequently:

- `kernel_ntt(plain)` output is **plain-modular** (no residual R factor).
- `kernel_basemul(a, b)` output has an **implicit factor of R⁻¹**.
- `kernel_invntt(x)` output has an **implicit factor of R** (from F_MONT).

The composer bridges these back to Z_q in host Python, mirroring the M32b /
M32e Montgomery bridge pattern established for Kyber. See
`docs/M32e_DESIGN.md` §"NTT convention and the Montgomery bridge".

A chained ntt → basemul → invntt round trip cancels R exactly:

    R⁻¹ · R = 1

so the composer gets a plain-modular product with no post-scale needed on
that specific path (used by `KeyGen` when computing `t = A ∘ s₁ + s₂`, by
`Sign` when computing `Az`, by `Verify` when computing `w' = Az − ct₁·2ᵈ`).

## Kernel dispatch signature

```c
extern "C" void dilithium_ntt(uint8_t mode,
                              int32_t in_a[256],
                              int32_t in_b[256],
                              int32_t out_c[256]);
```

Mirrors the M32b template exactly. `in_b` is only read for `MODE_BASEMUL`
(mode == 2) but is present in the signature to keep the AIE2 harness identical
across primitives.

## Native silicon gate

`phoenix_sdr_dsp.silicon.m33a_runner` now implements the M32-style
MLIR-AIE/IRON path. To respect the Phoenix XDNA1 core tile's two-input-DMA
limit, it sends `in_a[256]` in one ObjectFifo and packs `mode` plus
`in_b[256]` into a second 257-lane ObjectFifo. It retrieves the 256-lane
output through XRT. The gate prints `Backend: m33a:silicon` when the native
runtime preflight succeeds. If IRON/XRT is unavailable, the gate exits nonzero
with `m33a:unavailable`; it does **not** report a Python
transliteration as a silicon pass. Static transliteration checks validate
constants and source shape only.

Phoenix laptop silicon gate recorded on 2026-08-17:
`Backend: m33a:silicon`, **420/420 PASS** across NTT, INTT, base
multiplication, reduction, and end-to-end polynomial multiplication. See
[`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md).

## Provenance and audit

- Zetas table matches the published pq-crystals reference implementation
  ([ref/ntt.c](https://github.com/pq-crystals/dilithium/blob/master/ref/ntt.c))
  for all 256 entries (index 0 is 0 in both — never used in butterflies).
- `mont_reduce` explicitly computes the low 32 bits of the `QINV` product and
  reconstructs that word as signed before the final multiply by `q`. This
  preserves the pq-crystals reduction semantics without relying on signed
  `int64_t` overflow for legal base-multiplication inputs.
- Constants Q, QINV, F_MONT, MONT_R_MOD verified by
  `tools/m33a_kernel_transliteration_check.py` against first-principles
  derivations, and against the pq-crystals ref-C values.
- Ground truth for gate testing is `dilithium-py v1.4.0`
  (Python port of pq-crystals dilithium, `pip install dilithium-py`).

## Downstream milestones

| ID     | Component                                                       | Status  |
|:-------|:----------------------------------------------------------------|:--------|
| M33a   | Dilithium NTT / INTT / BASEMUL / REDUCE (this doc)              | Phoenix silicon: 420/420 PASS |
| M33b   | SampleInBall, Power2Round, Decompose (HighBits / LowBits), MakeHint / UseHint | Phoenix silicon: 700/700 PASS |
| M33c   | SHAKE128 / SHAKE256 (reuse M32c kernel unchanged)                | Reuse   |
| M33d   | KeyGen composer (FIPS 204 Alg 1 / 6), all 3 param sets           | Hybrid host/NPU: 75/75 PASS |
| M33e   | Sign + Verify composer with rejection loop, ACVP KATs 44/65/87   | Hybrid host/NPU: 180/180 PASS |

The primitive silicon and hybrid-composer results are recorded separately;
they are not represented as a single count of fully device-resident milestones.
M33c is a reuse of existing SHAKE work and does not
consume a contract slot.

## References

- FIPS 204, *Module-Lattice-Based Digital Signature Standard*, NIST, 13 Aug 2024. <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- pq-crystals dilithium reference implementation (C). <https://github.com/pq-crystals/dilithium/tree/master/ref>
- `dilithium-py` — GiacomoPope, Python port, v1.4.0. <https://github.com/GiacomoPope/dilithium-py>
- NIST ACVP-Server ML-DSA test vectors. <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>
- Ducas et al., *CRYSTALS-Dilithium: A Lattice-Based Digital Signature Scheme*, IACR ToCHES 2018. <https://eprint.iacr.org/2017/633>
