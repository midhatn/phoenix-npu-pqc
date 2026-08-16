# M33d — ML-DSA KeyGen composer (FIPS 204)

Post-Quantum Cryptography — FIPS 204 ML-DSA (Dilithium) key generation on
Phoenix NPU. This milestone assembles the previous per-primitive silicon
kernels (M33a NTT, M33b rounding, M32c SHAKE reused as M33c) into an
end-to-end KeyGen implementing Algorithm 6 of FIPS 204 for all three
parameter sets in a single composer.

## Scope

- **In silicon**: coefficient-wise NTT / INTT / basemul (M33a modes 0/1/2),
  Power2Round (M33b mode 0), and every SHAKE128 / SHAKE256 absorb-squeeze
  used by ExpandA, ExpandS, `H`, and `tr = H(pk, 64)` (M32c, reused
  unchanged from M33c — no new tile slot).
- **In host Python**: rejection sampling loops driven by SHAKE output
  (`RejNTTPoly`, `RejBoundedPoly`), bit-packing (`_pack_pk`, `_pack_sk`,
  `bit_pack_t1`, `bit_pack_t0`, `bit_pack_s`), and the tiny linear-time
  matrix-vector accumulation. These are either data-dependent branchy
  state machines or O(bytes) glue — the wrong shape for AIE tiles.

## Composer shape (Alg 6, FIPS 204)

```text
seed_bytes  = SHAKE256(zeta || [k] || [ell], 128)                  # M32c
rho, rho', K = seed_bytes[:32], seed_bytes[32:96], seed_bytes[96:]

A_hat[i][j] = RejNTTPoly(SHAKE128(rho || [j,i]))         for i<k, j<ell  # M32c inside
s1[j]       = RejBoundedPoly(SHAKE256(rho' || j),  eta)  for j<ell        # M32c inside
s2[i]       = RejBoundedPoly(SHAKE256(rho' || l+i), eta)  for i<k         # M32c inside

s1_hat[j]   = NTT(s1[j])                                for j<ell         # M33a mode 0

for i<k:
    acc = 0
    for j<ell:
        acc += basemul(A_hat[i][j], s1_hat[j])                            # M33a mode 2
    t_hat[i] = acc

t[i]  = INTT(t_hat[i]) + s2[i]                          for i<k           # M33a mode 1
t1[i], t0[i] = Power2Round(t[i], d=13)                  for i<k           # M33b mode 0

pk = rho || bit_pack_t1(t1)
tr = SHAKE256(pk, 64)                                                     # M32c
sk = rho || K || tr || bit_pack_s(s1) || bit_pack_s(s2) || bit_pack_t0(t0)
```

## Parameter sets (all three land together)

| Set        | k | ell | eta | pk size | sk size |
|:-----------|--:|----:|----:|--------:|--------:|
| ML-DSA-44  | 4 | 4   | 2   | 1312 B  | 2560 B  |
| ML-DSA-65  | 6 | 5   | 4   | 1952 B  | 4032 B  |
| ML-DSA-87  | 8 | 7   | 2   | 2592 B  | 4896 B  |

All three share the same ring, NTT twiddle table, and Power2Round split
point `d = 13` — only k, ell, eta, and packing widths change.

## Silicon dispatch abstraction

`SiliconBackend` in `tests/m33_mldsa/mldsa_composer.py` exposes:

```python
poly_ntt(coeffs)          -> list[int]      # M33a mode 0
poly_invntt(coeffs)       -> list[int]      # M33a mode 1
poly_basemul(a, b)        -> list[int]      # M33a mode 2
poly_add_mod(a, b)        -> list[int]      # host (trivial)
poly_power2round(coeffs)  -> (r1, r0)       # M33b mode 0
```

Each primitive keeps its I/O in **plain modular** form `[0, q)`. The
Montgomery R factor introduced by the NTT is stripped in `poly_invntt` and
`poly_basemul` via one host multiply by `R_INV_MOD_Q` or `R_MOD_Q`. This
matches how M32e wraps the ML-KEM NTT kernel, so downstream Sign/Verify
(M33e) can reuse the same conversion conventions.

When silicon runners `phoenix_sdr_dsp.silicon.m33a_runner` and
`phoenix_sdr_dsp.silicon.m33b_runner` are importable, they replace the
Python fallbacks — same test file, same 75 KATs, byte-identical outputs.

## Rationale: what stays in host, and why

| Step                       | Location | Rationale |
|:---------------------------|:---------|:----------|
| ExpandA rejection loop     | host     | Rejection over 24-bit fields with data-dependent early exit. Wrong shape for a fixed-latency tile. |
| ExpandS rejection loop     | host     | Same — rejection over 4-bit nibbles vs eta bound. |
| Matrix-vector accumulator  | host     | k·ell = 32 additions worst case; each add is 256 int32 adds. Host CPU is faster than round-tripping through DMA. |
| bit_pack_t1 / t0 / s       | host     | Sequential 10-bit / 13-bit / eta-bit packing. |
| SHAKE128 / SHAKE256        | **M33c (=M32c)** | Already deployed and validated on ML-KEM. No new slot. |

Sign and Verify (M33e) will add: `SampleInBall` (host, sequential rejection),
`HighBits` / `LowBits` / `MakeHint` / `UseHint` (all in M33b modes 1-4), norm
checks (M33b mode 4), and the rejection retry loop over rho'' — all glue
that reuses this same composer skeleton.

## Gate

Vectors: `tests/m33_mldsa/vectors/ML-DSA-keyGen-FIPS204_{prompt,expectedResults}.json`
sourced verbatim from
[NIST usnistgov/ACVP-Server](https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files).
25 tests per parameter set, 75 total.

### Sandbox results (reference path)

    ML-DSA-44      25/25    PASS
    ML-DSA-65      25/25    PASS
    ML-DSA-87      25/25    PASS
    ----------------------------
    TOTAL          75/75    PASS      (~1.1s wall)

    transliteration check:  15/15 PASS

Laptop silicon gate: TBD.

## Files

| Path                                                     | Role                                              |
|:---------------------------------------------------------|:--------------------------------------------------|
| `tests/m33_mldsa/mldsa_composer.py`                      | Composer + SiliconBackend abstraction              |
| `tests/m33_mldsa/test_mldsa_keygen_m33d.py`              | Two-stage gate (ref + silicon) against 75 ACVP KATs |
| `tools/m33d_kernel_transliteration_check.py`             | Static composer-shape + Montgomery constants check |
| `docs/M33d_DESIGN.md`                                    | This document                                     |

## Contract path

    30/30 (M33a) -> 31/31 (M33b) -> [M33c reuse, no slot]
        -> 32/32 (M33d, this milestone) -> 33/33 (M33e Sign+Verify)

## References

- FIPS 204, *Module-Lattice-Based Digital Signature Standard*, NIST, 13 Aug 2024. <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- pq-crystals dilithium reference. <https://github.com/pq-crystals/dilithium>
- `dilithium-py` v1.4.0. <https://github.com/GiacomoPope/dilithium-py>
- NIST ACVP-Server ML-DSA test vectors. <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>
