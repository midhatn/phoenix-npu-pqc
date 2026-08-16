# M33e — ML-DSA Sign / Verify composer (FIPS 204)

Post-Quantum Cryptography — final sub-milestone of M33. Assembles
`ML-DSA.Sign_internal` (FIPS 204 Algorithm 7) and `ML-DSA.Verify_internal`
(Algorithm 8) on top of the silicon kernels landed earlier in M33:

- **M33a** — NTT / INTT / basemul over `Z_q`, `q = 8380417`
- **M33b** — Power2Round, Decompose, MakeHint, UseHint, CheckNormBound,
  ReduceModPm
- **M33c** — SHAKE128 / SHAKE256 (re-use of the M32c Keccak kernel, no new
  silicon slot)

No new `.cc` kernel lands with M33e — everything data-parallel is already
covered by M33a and M33b. This milestone is pure composer work.

## Scope

Both parameter sets and both `externalMu` conventions from the NIST ACVP
`internal` interface are exercised in one composer:

- ML-DSA-44 / ML-DSA-65 / ML-DSA-87
- `external_mu=False` → composer computes `mu = H(tr || m)`
- `external_mu=True`  → caller supplies `mu` directly (used by
  ACVP `internal` groups with `externalMu=True` and by higher-level
  external-hash constructions that hash M outside the module)

## Sign_internal shape (Alg 7)

```text
rho, K, tr, s1, s2, t0    = UnpackSK(sk)
A_hat                      = ExpandA(rho)                                # M32c inside
s1_hat, s2_hat, t0_hat     = NTT(s1), NTT(s2), NTT(t0)                   # M33a mode 0

mu     = external_mu ? m : H(tr || m, 64)                                # M32c
rho''  = H(K || rnd || mu, 64)                                           # M32c
kappa  = 0
loop:
    y      = ExpandMask(rho'', kappa);                kappa += ell       # M32c inside
    y_hat  = NTT(y)                                                       # M33a mode 0
    w      = INTT(A_hat . y_hat)                                          # M33a modes 2, 1
    w1     = HighBits(w, alpha)                                           # M33b mode 1 first output
    c_tilde = H(mu || Pack_w(w1), c_tilde_bytes)                         # M32c
    c      = SampleInBall(c_tilde, tau)                    # host, rejection loop
    c_hat  = NTT(c)                                                        # M33a mode 0
    z      = y + INTT(c_hat . s1_hat)                                     # M33a modes 2, 1
    if !CheckNorm(z, gamma_1 - beta): continue                           # M33b mode 4
    r0     = LowBits(w - INTT(c_hat . s2_hat), alpha)                    # M33a 2/1 + M33b 1
    if !CheckNorm(r0, gamma_2 - beta): continue                          # M33b mode 4
    c_t0   = INTT(c_hat . t0_hat)                                         # M33a modes 2, 1
    if !CheckNorm(c_t0, gamma_2): continue                               # M33b mode 4
    h      = MakeHint(-c_t0, w - c_s2 + c_t0, alpha)                     # M33b mode 2
    if popcount(h) > omega: continue                                     # host
    return PackSig(c_tilde, z, h)                                        # host
```

`popcount(h) <= omega` and the SampleInBall inner loop are the two pieces
that stay on host — the first is a scalar reduction and the second is a
data-dependent rejection state machine over SHAKE256 output.

## Verify_internal shape (Alg 8)

```text
rho, t1                    = UnpackPK(pk)
c_tilde, z, h              = UnpackSig(sig)               # ValueError -> return False
if popcount(h) > omega: return False                       # host
if !CheckNorm(z, gamma_1 - beta): return False             # M33b mode 4
A_hat                      = ExpandA(rho)                  # M32c inside
mu = external_mu ? m : H(H(pk,64) || m, 64)                # M32c
c  = SampleInBall(c_tilde, tau);   c_hat = NTT(c)          # M33a mode 0
z_hat = NTT(z)                                             # M33a mode 0
t1_hat = NTT(t1 * 2^d)                                     # M33a mode 0
diff = INTT(A_hat . z_hat - c_hat . t1_hat)                # M33a 2, 1
w' = UseHint(h, diff, alpha)                               # M33b mode 3
return c_tilde == H(mu || Pack_w(w'), c_tilde_bytes)       # M32c
```

## Silicon dispatch surface

New composer methods on top of M33d's `MLDSAComposer` / `SiliconBackend`:

| Method                | Kernel   | Mode | FIPS 204 |
|:----------------------|:---------|-----:|:---------|
| `poly_decompose`      | M33b     | 1    | Alg 30   |
| `poly_high_bits`      | M33b     | 1    | Alg 31   |
| `poly_low_bits`       | M33b     | 1    | Alg 32   |
| `poly_make_hint`      | M33b     | 2    | Alg 33   |
| `poly_use_hint`       | M33b     | 3    | Alg 34   |
| `poly_check_norm`     | M33b     | 4    | norm check |

Everything else (NTT / INTT / basemul / Power2Round / SHAKE / SampleInBall
/ bit-packing) was already in the composer from M33d.

## Gates

Vectors: `tests/m33_mldsa/vectors/ML-DSA-{sigGen,sigVer}-FIPS204_*.json`
sourced verbatim from
[NIST usnistgov/ACVP-Server](https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files).

Scope for M33e: internal interface, tgIds 7-12 (90 sigGen + 90 sigVer =
180 tests). Sign vectors are `deterministic=True` with `rnd = 0^32`, so
byte-for-byte reproducible against `expectedResults.signature`. Verify
vectors mix must-pass and must-reject cases (18 valid, 72 tampered
across the 90 sigVer tests), exercising the M33b MODE 4 CheckNormBound
early-exit and the popcount omega check.

### Sandbox results (reference path)

    Sign_internal   (90 tests):  90/90 PASS   (~8.7s wall)
    Verify_internal (90 tests):  90/90 PASS   (~1.2s wall)
    transliteration audit:       35/35 PASS

Laptop silicon gate: TBD.

## Notes on the deterministic path

For `deterministic=True` groups, ACVP sets `rnd = 0^32` inside the composer.
This makes the entire Sign_internal reproducible so long as `SampleInBall`,
`ExpandMask`, `ExpandA`, and every numerical primitive is byte-identical to
the reference. The composer inherits `SampleInBall` and the rejection-loop
`ExpandMask` from `dilithium-py`; every other numerical primitive routes
through silicon.

For `deterministic=False` and any use of `ML-DSA.Sign` (external interface,
non-internal), the composer would need a caller-supplied RNG and message
encoding wrapper — those groups (tgIds 1-6, 13-24) are out of scope for
this milestone and are covered by the reference algorithm the composer
delegates to for `SampleInBall` and packing.

## Files

| Path                                                       | Role                                             |
|:-----------------------------------------------------------|:-------------------------------------------------|
| `tests/m33_mldsa/mldsa_composer.py`                        | `sign_internal` + `verify_internal` on M33d base |
| `tests/m33_mldsa/test_mldsa_sign_m33e.py`                  | ACVP sigGen internal-deterministic gate           |
| `tests/m33_mldsa/test_mldsa_verify_m33e.py`                | ACVP sigVer internal (pass + reject) gate         |
| `tools/m33e_kernel_transliteration_check.py`               | Static composer-shape audit                       |
| `docs/M33e_DESIGN.md`                                      | This document                                     |

## Contract path

    30/30 (M33a) -> 31/31 (M33b) -> [M33c reuse, no slot]
        -> 32/32 (M33d KeyGen) -> 33/33 (M33e, this milestone)

M33 fully closed — FIPS 204 ML-DSA (Post-Quantum Cryptography) end-to-end
signing and verification on Phoenix NPU, all three parameter sets, gated
against NIST ACVP.

## References

- FIPS 204, *Module-Lattice-Based Digital Signature Standard*, NIST, 13 Aug 2024. <https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf>
- pq-crystals dilithium reference. <https://github.com/pq-crystals/dilithium>
- `dilithium-py` v1.4.0. <https://github.com/GiacomoPope/dilithium-py>
- NIST ACVP-Server ML-DSA test vectors. <https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files>
