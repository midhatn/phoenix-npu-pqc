# M33d — ML-DSA KeyGen composer (FIPS 204)

Post-Quantum Cryptography — FIPS 204 ML-DSA (Dilithium) key generation using
a host-orchestrated Phoenix NPU composer. This milestone invokes M33a NTT and
M33b rounding primitives on silicon while Python implements Algorithm 6
control, SHAKE, sampling, accumulation, and packing for all three parameter
sets.

## Scope

- **In silicon**: coefficient-wise NTT / INTT / basemul (M33a modes 0/1/2)
  and Power2Round (M33b mode 0).
- **In host Python**: SHAKE128 / SHAKE256, rejection sampling loops
  (`RejNTTPoly`, `RejBoundedPoly`), bit-packing (`_pack_pk`, `_pack_sk`,
  `bit_pack_t1`, `bit_pack_t0`, `bit_pack_s`), and the tiny linear-time
  matrix-vector accumulation. Moving these operations to a fused device graph
  is future work; this gate does not claim fully NPU-resident KeyGen.

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

The composer test constructs `SiliconBackend` from
`phoenix_sdr_dsp.silicon.m33a_runner.run` and
`phoenix_sdr_dsp.silicon.m33b_runner.run`. Both are native-only dispatchers:
if either runtime is unavailable, the test exits nonzero rather than running a
partial or reference backend. A default `SiliconBackend()` also chooses these
native runners; `reference_for_unit_tests()` is explicitly named and is not
silicon evidence.

## Rationale: what stays in host, and why

| Step                       | Location | Rationale |
|:---------------------------|:---------|:----------|
| ExpandA rejection loop     | host     | Rejection over 24-bit fields with data-dependent early exit. Wrong shape for a fixed-latency tile. |
| ExpandS rejection loop     | host     | Same — rejection over 4-bit nibbles vs eta bound. |
| Matrix-vector accumulator  | host     | k·ell = 32 additions worst case; each add is 256 int32 adds. Host CPU is faster than round-tripping through DMA. |
| bit_pack_t1 / t0 / s       | host     | Sequential 10-bit / 13-bit / eta-bit packing. |
| SHAKE128 / SHAKE256        | host | The current M33 composer calls `dilithium-py`; it does not dispatch M32c. |

Sign and Verify (M33e) will add: `SampleInBall` (host, sequential rejection),
`HighBits` / `LowBits` / `MakeHint` / `UseHint` (all in M33b modes 1-4), norm
checks (M33b mode 4), and the rejection retry loop over rho'' — all glue
that reuses this same composer skeleton.

## Gate

Vectors: `tests/m33_mldsa/vectors/ML-DSA-keyGen-FIPS204_{prompt,expectedResults}.json`
sourced verbatim from
[NIST usnistgov/ACVP-Server](https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files).
25 tests per parameter set, 75 total.

### Native gate status

The test reports `Backend: m33a:silicon, m33b:silicon` only after both native
runner modules and their MLIR-AIE runtime preflight are available. It is
intentionally nonzero on a sandbox/no-NPU host, so no reference KAT result is
presented as hardware proof. Static composer and kernel audits remain
host-only checks.

Laptop validation recorded 2026-08-17 on the Phoenix XDNA1 host:
`Backend: m33a:silicon, m33b:silicon`, with ML-DSA-44, ML-DSA-65, and
ML-DSA-87 each passing 25/25 ACVP KeyGen vectors (**75/75 total**). This is
evidence for the host-orchestrated composer and its native polynomial
dispatches, not for device-resident SHAKE, sampling, packing, or control.

## Files

| Path                                                     | Role                                              |
|:---------------------------------------------------------|:--------------------------------------------------|
| `tests/m33_mldsa/mldsa_composer.py`                      | Composer + SiliconBackend abstraction              |
| `tests/m33_mldsa/test_mldsa_keygen_m33d.py`              | Native-only gate against 75 ACVP KATs |
| `tools/m33d_kernel_transliteration_check.py`             | Static composer-shape + Montgomery constants check |
| `docs/M33d_DESIGN.md`                                    | This document                                     |

## Contract path

    Entry 30: M33a -> entry 31: M33b -> [M33c reuse, no slot]
        -> entry 32: M33d -> entries 33-34: M33e Sign and Verify

These entry numbers describe the 34-invocation mixed-backend regression matrix,
not a count of fully device-resident workloads.

## References

- FIPS 204, *Module-Lattice-Based Digital Signature Standard*, NIST, 13 Aug 2024. <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- pq-crystals dilithium reference. <https://github.com/pq-crystals/dilithium>
- `dilithium-py` v1.4.0. <https://github.com/GiacomoPope/dilithium-py>
- NIST ACVP-Server ML-DSA test vectors. <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>
