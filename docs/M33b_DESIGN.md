# M33b — Dilithium rounding / hint primitives (FIPS 204 ML-DSA)

Post-Quantum Cryptography — FIPS 204 (ML-DSA) primitive layer, silicon side.
This milestone lands the coefficient-wise rounding, decomposition, hint, and
norm-check primitives used by ML-DSA-44 / ML-DSA-65 / ML-DSA-87 for KeyGen,
Sign, and Verify.

## Scope

Kernel: `tests/m33_mldsa/dilithium_sampler_kernel.cc`, six modes.

| mode | operation           | called from    | in_a          | in_b            | out_c                            | out_d           |
|-----:|:--------------------|:---------------|:--------------|:----------------|:---------------------------------|:----------------|
| 0    | Power2Round(d=13)   | KeyGen (t split)         | 256 × int32   | —               | r₁ (256 × int32)                 | r₀ (256 × int32) |
| 1    | Decompose(α)        | Sign (w → w₁,w₀)         | 256 × int32   | —               | r₁ (256 × int32)                 | r₀ (256 × int32) |
| 2    | MakeHint(α)         | Sign (build h)           | z (256 × int32) | r (256 × int32) | h ∈ {0,1} (256 × int32)          | —                |
| 3    | UseHint(α)          | Verify (recover w'₁)     | h (256 × int32) | r (256 × int32) | r'₁ (256 × int32)                | —                |
| 4    | CheckNormBound(b)   | Sign/Verify coefficient-norm check | 256 × int32 | — | out_c[0] = 1 if all pass, else 0 | —                |
| 5    | ReduceModPm         | utility (canonical form) | 256 × int32   | —               | r' ∈ (−q/2, q/2]                 | —                |

**SampleInBall is intentionally not in this kernel.** Its inner loop is a
rejection-sample-and-swap state machine over SHAKE256 output — inherently
sequential and irregular. It stays in the M33d/e host composer as a Python
reference call; putting it on tiles would cost more than the fixed-latency
data-parallel modes gain.

## Parameters per ML-DSA set

| Set        | γ₂            | α = 2γ₂     | β         | γ₁ − β   | ω  |
|:-----------|--------------:|------------:|----------:|---------:|---:|
| ML-DSA-44  | (q−1)/88 = 95232  | 190464 | 78        | 130994   | 80 |
| ML-DSA-65  | (q−1)/32 = 261888 | 523776 | 196       | 524092   | 55 |
| ML-DSA-87  | (q−1)/32 = 261888 | 523776 | 120       | 524168   | 75 |

`d = 13` (Power2Round split point) is the same for all parameter sets per
FIPS 204 Table 1.

## Kernel signature

```c
extern "C" void dilithium_sampler(uint8_t  mode,
                                  int32_t  param,
                                  int32_t  in_a[256],
                                  int32_t  in_b[256],
                                  int32_t  out_c[256],
                                  int32_t  out_d[256]);
```

- `param` carries α for Decompose / MakeHint / UseHint, and the norm bound b
  for CheckNorm. Unused in Power2Round / ReduceModPm.
- `out_d` is only written by Power2Round and Decompose.

## Semantics notes

**Power2Round** (FIPS 204 Alg 29): `r₁ = (r − r₀) / 2ᵈ, r₀ = r mod± 2ᵈ`,
computed via `r₀ = r & (2ᵈ−1); if r₀ > 2^(d−1): r₀ -= 2ᵈ`.

**Decompose** (Alg 30): standard split plus the edge case `r₁·α = q−1` where
the reference sets `r₁ = 0, r₀ = r₀ − 1` so that r₁ stays in `[0, (q−1)/α)`.

**MakeHint** (Alg 33): 1-bit flag `HighBits(r+z) ≠ HighBits(r)`. The composer
supplies both operands; the kernel does two Decompose calls per coefficient
under the hood.

**UseHint** (Alg 34): given h and r, returns the hint-adjusted high bits of
r by optionally nudging `r₁` up or down by one modulo `m = (q−1)/α`. When
`h = MakeHint(z, r)` under the algorithm preconditions, the result equals
`HighBits(r+z)`.

**CheckNormBound**: reduces each coefficient to `(−q/2, q/2]`, takes absolute
value, checks all coeffs are `< b`. Returns single bit in `out_c[0]` (rest of
`out_c` undefined). Composer treats out_c[0] = 0 as reject. Signature hint
weight is a separate host-side `popcount(h)` check, not this coefficient-norm
operation.

## Composer bridge

Unlike M33a / M32b, these primitives operate entirely on **plain Z_q** — no
Montgomery domain semantics. The composer passes coefficients as int32 in
either signed form or in `[0, q)`; both are accepted (`canonicalize()`
normalizes to `[0, q)` inside the kernel).

## Native silicon gate

`phoenix_sdr_dsp.silicon.m33b_runner` now implements the M32-style
MLIR-AIE/IRON path. To fit the Phoenix XDNA1 two-input-DMA limit, it sends
`in_a[256]` in one ObjectFifo and packs `mode`, `param`, and `in_b[256]` into
a second 258-lane ObjectFifo. It drains two 256-lane int32 outputs through
XRT. The gate prints `Backend: m33b:silicon` after native runtime preflight.
If IRON/XRT is unavailable, it exits nonzero with
`m33b:unavailable`; it does **not** turn the Python transliteration into a
silicon pass.

Phoenix laptop silicon gate recorded on 2026-08-17:
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=m33b_design; classification=SELF_REPORTED_UNVERIFIED] -->
`Backend: m33b:silicon`, **700/700 PASS** across Power2Round, Decompose,
MakeHint, UseHint, CheckNorm, and reduce-to-centered-range gates. See
[`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md).

## Downstream

| ID     | Component                                                       | Status  |
|:-------|:----------------------------------------------------------------|:--------|
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=m33b_design; classification=SELF_REPORTED_UNVERIFIED] -->
| M33a   | Dilithium NTT / INTT / BASEMUL / REDUCE                          | Phoenix silicon: 420/420 PASS |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=m33b_design; classification=SELF_REPORTED_UNVERIFIED] -->
| M33b   | rounding / hint / norm-check primitives (this doc)               | Phoenix silicon: 700/700 PASS |
| M33c   | reuse M32c SHAKE128 / SHAKE256 kernel                            | Reuse   |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=m33b_design; classification=SELF_REPORTED_UNVERIFIED] -->
| M33d   | KeyGen composer (Alg 1 / 6), 3 param sets, ACVP KeyGen KATs      | Hybrid host/NPU: 75/75 PASS |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=m33b_design; classification=SELF_REPORTED_UNVERIFIED] -->
| M33e   | Sign / Verify composer, rejection loop, ACVP sigGen / sigVer     | Hybrid host/NPU: 180/180 PASS |

The primitive silicon and hybrid-composer results are recorded separately;
they are not represented as a single count of fully device-resident milestones.

## References

- FIPS 204, *Module-Lattice-Based Digital Signature Standard*, NIST, 13 Aug 2024. <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- pq-crystals dilithium reference, `ref/rounding.c`. <https://github.com/pq-crystals/dilithium/blob/master/ref/rounding.c>
- `dilithium-py` v1.4.0. <https://github.com/GiacomoPope/dilithium-py>
- NIST ACVP-Server ML-DSA test vectors. <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>
