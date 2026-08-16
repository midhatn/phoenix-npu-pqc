# M32e — ML-KEM-512 end-to-end on Phoenix NPU (PQC)

## Purpose

M32e is the capstone of Track 4 (Post-Quantum Cryptography, PQC) in the
`phoenix-sdr-dsp` roadmap. It composes the three previously-landed PQC
primitive kernels — **M32b** (NTT / INTT / MultiplyNTTs / PolyAdd / PolySub),
**M32c** (SHA-3-256, SHA-3-512, SHAKE128, SHAKE256, SampleNTT, SamplePolyCBD),
and **M32d** (Compress / Decompress d=4 & d=10, ByteEncode / ByteDecode d=12,
poly frommsg / tomsg) — into a full FIPS 203 ML-KEM-512 KEM: KeyGen,
Encapsulation, and Decapsulation. Every internal primitive dispatches to the
Phoenix AI NPU (AIE2). The composition itself runs as pure Python on the host
laptop, so a full KEM operation is a sequence of ~30 (KeyGen) / ~40 (Encaps) /
~70 (Decaps) round-trip DMAs between the host and the NPU.

**Post-Quantum Cryptography context.** ML-KEM-512 is the NIST-standardized
key-encapsulation mechanism from FIPS 203 (August 2024), category 1 (AES-128
security). It is the direct FIPS 203 codification of CRYSTALS-Kyber-512 from
NIST's PQC standardization competition. This milestone completes an end-to-end
PQC KEM whose every arithmetic and symmetric primitive lives on the NPU.

## Deliverables

| File | Purpose |
|---|---|
| `tests/m32_mlkem/mlkem_composer.py` | Pure-Python FIPS 203 K-PKE + ML-KEM.Internal composition on top of a `Backend` abstraction; ships with a `HostBackend` (CPU reference) and a `SiliconBackend` (dispatches to M32b/M32c/M32d) |
| `tests/m32_mlkem/test_mlkem_m32e.py` | Pytest suite: 60 reference gates (HostBackend vs NIST ACVP) + 9 silicon gates (SiliconBackend, small smoke subset) + `M32E_FULL_KAT=1` for full 60-vector silicon sweep |
| `tools/m32e_kernel_transliteration_check.py` | Independent second-source cross-check: `HostBackend` == `kyber-py v1.2.0` == NIST ACVP across all 60 KATs |
| `tests/m32_mlkem/vectors/` | Vendored NIST ACVP-Server ML-KEM-512 vectors (`keygen_prompt.json`, `keygen_expected.json`, `encapdecap_prompt.json`, `encapdecap_expected.json`) |
| `docs/M32e_DESIGN.md` | This document |
| `tests/m32_mlkem/keccak_shake_kernel.cc` (edited) | M32c kernel: `XOF_MAX_OUT` bumped from 504 → 840 (5 SHAKE128 rate blocks) to eliminate SampleNTT tail failures on unlucky NIST vectors |

## FIPS 203 algorithm mapping

The composer implements the FIPS 203 primitives verbatim. Each numbered
algorithm below is a single Python function in `mlkem_composer.py`; every
non-scalar operation is a `Backend` method call and therefore an NPU dispatch
when running under the silicon backend.

| FIPS 203 algorithm | Composer function | Primitive dispatches |
|---|---|---|
| **Alg 13** K-PKE.KeyGen(d) | `kpke_keygen` | `sha3_512`, `sample_ntt` × 4, `sample_poly_cbd` × 4, `ntt` × 4, `multiply_ntts` × 4, `poly_add` × 6, `poly_tobytes_d12` × 4 |
| **Alg 14** K-PKE.Encrypt(ek, m, r) | `kpke_encrypt` | `poly_frombytes_d12` × 2, `sample_ntt` × 4, `sample_poly_cbd` × 5, `ntt` × 2, `intt` × 3, `multiply_ntts` × 6, `poly_add` × 9, `poly_frommsg`, `compress_d10` × 2, `compress_d4` |
| **Alg 15** K-PKE.Decrypt(dk, c) | `kpke_decrypt` | `decompress_d10` × 2, `decompress_d4`, `poly_frombytes_d12` × 2, `ntt` × 2, `intt`, `multiply_ntts` × 2, `poly_add`, `poly_sub`, `poly_tomsg` |
| **Alg 16** ML-KEM.KeyGen_internal(d, z) | `mlkem_keygen_internal` | `kpke_keygen` + `sha3_256` |
| **Alg 17** ML-KEM.Encaps_internal(ek, m) | `mlkem_encaps_internal` | `sha3_256` + `sha3_512` + `kpke_encrypt` |
| **Alg 18** ML-KEM.Decaps_internal(dk, c) | `mlkem_decaps_internal` | `kpke_decrypt` + `sha3_512` + `shake256` + `kpke_encrypt` |

The composer stops one level short of the full FIPS 203 Encaps/Decaps (Alg 20 /
Alg 21) because those add public-key/decap-key validation only and use the
same `_internal` core. NIST ACVP tests exercise the `_internal` variants
directly.

## Composition topology

```
       ┌───────────── laptop (host, Python) ─────────────┐
       │                                                  │
KeyGen │  d,z ─► sha3_512 ┐            ┌─► ntt   ─► mul   │
       │                  ├── expand   │              +   ├── ek || dk
       │  rho,sigma       │  matrix    │              e   │
       │                  └─► sample_ntt (×4)          │  │
       │                       sample_cbd (×4) ────────┘  │
       │                                                  │
       │              (each arrow = round-trip DMA        │
       │               into the Phoenix NPU AIE2 tile)    │
       │                                                  │
       └──────────────────────────────────────────────────┘
                 │                          ▲
                 │ 34 B seeds / int16 polys / <=1 KB byte streams
                 ▼                          │
       ┌───────── Phoenix NPU (AIE2) ────────┐
       │  M32c: SHA-3 / SHAKE / SampleNTT    │
       │  M32b: NTT / INTT / MultiplyNTTs    │
       │  M32d: Compress / Encode / message  │
       └─────────────────────────────────────┘
```

The three silicon kernels are compiled independently (each is its own
`@iron.jit` program with its own object-fifo topology of `2 input + 1 output`).
`SiliconBackend.__init__` imports the sibling `_dispatch`/`_pack_ctrl` helpers
from `test_ntt_m32b.py`, `test_keccak_shake_m32c.py`, and `test_kpke_m32d.py`,
so the same JIT-compiled programs that pass those milestones' silicon gates
handle every M32e operation.

## Correctness strategy

Four independent axes gate correctness:

1. **Composer vs NIST ACVP.** `HostBackend` composed FIPS 203 KEM matches the
   25 KeyGen, 25 Encap, and 10 Decap NIST ACVP-Server ML-KEM-512 test vectors
   byte-for-byte. Run via `python -m pytest tests/m32_mlkem/test_mlkem_m32e.py`.

2. **Composer vs second-source Python.** `tools/m32e_kernel_transliteration_check.py`
   checks that `HostBackend` composed FIPS 203 KEM matches
   [kyber-py v1.2.0](https://pypi.org/project/kyber-py/) byte-for-byte on all
   60 KATs. `kyber-py` is fully independent of `pq-crystals` reference C —
   different author (GiacomoPope), pure Python, positive-residue representation
   throughout. Since `kyber-py` also passes all 60 NIST vectors, a three-way
   agreement (composer / kyber-py / NIST) is strong evidence of no
   transliteration errors.

3. **Silicon primitives vs host primitives.** M32b, M32c, and M32d silicon
   gates (already PASS 5/5, 12/12, 8/8 on Ryzen 9 7940HS Phoenix NPU1) prove
   each primitive is bit-exact against its Python reference.

4. **Silicon composition vs NIST.** `test_mlkem_m32e.py` runs
   `SiliconBackend` (composed on-NPU) against a smoke set of 3 NIST KATs per
   axis by default; the full 60-KAT sweep runs when `M32E_FULL_KAT=1`.

## Known-answer test vectors

**Source: NIST ACVP-Server** (Automated Cryptographic Validation Protocol
server), the official NIST test-vector service for FIPS 203 conformance
testing:

- Repository: [github.com/usnistgov/ACVP-Server](https://github.com/usnistgov/ACVP-Server)
- Vendored path: `tests/m32_mlkem/vectors/`
- Sources:
  - [ML-KEM-keyGen-FIPS203/prompt.json](https://github.com/usnistgov/ACVP-Server/blob/master/gen-val/json-files/ML-KEM-keyGen-FIPS203/prompt.json)
  - [ML-KEM-keyGen-FIPS203/expectedResults.json](https://github.com/usnistgov/ACVP-Server/blob/master/gen-val/json-files/ML-KEM-keyGen-FIPS203/expectedResults.json)
  - [ML-KEM-encapDecap-FIPS203/prompt.json](https://github.com/usnistgov/ACVP-Server/blob/master/gen-val/json-files/ML-KEM-encapDecap-FIPS203/prompt.json)
  - [ML-KEM-encapDecap-FIPS203/expectedResults.json](https://github.com/usnistgov/ACVP-Server/blob/master/gen-val/json-files/ML-KEM-encapDecap-FIPS203/expectedResults.json)

The full ACVP files cover all three parameter sets (ML-KEM-512 / -768 / -1024);
only the ML-KEM-512 `testGroups` (tgId 1 for KeyGen; tgId 1 for encapsulation,
tgId 4 for decapsulation; a total of 25 + 25 + 10 = 60 vectors) are retained.
`encapsulationKeyCheck` (tgId 8) and `decapsulationKeyCheck` (tgId 7) groups
are intentionally excluded — they test *invalid* input rejection, not KEM
compliance, and are outside M32e scope.

## SampleNTT byte budget: M32c XOF_MAX_OUT bump

FIPS 203 Algorithm 6 (SampleNTT) is a rejection sampler: it consumes 3 bytes
of SHAKE128(rho || j || i) output at a time, accepts each 12-bit little-endian
sample below `q=3329`, and stops after 256 accepted coefficients. The number
of SHAKE128 bytes consumed per SampleNTT call is a random variable; the mean
is ~236 bytes but the tail can be arbitrarily long.

The M32c kernel prior to M32e capped SampleNTT XOF output at 504 bytes
(3 rate blocks). Empirically, across the 25 NIST ML-KEM-512 KeyGen vectors
(each performing 4 SampleNTT calls to build A_hat = 2×2 matrix in NTT domain
= 100 total SampleNTT invocations), **3 calls required more than 504 bytes**,
with a worst case of **516 bytes** at tcId=20. Those would silently zero-pad
the trailing coefficients, producing wrong A_hat and failing KAT match.

**Fix (this milestone).** Bump `XOF_MAX_OUT` from 504 → **840 bytes**
(5 SHAKE128 rate blocks) in `tests/m32_mlkem/keccak_shake_kernel.cc`, and
correspondingly bump `MAX_OUT_BYTES` 512 → 1024 to keep the DMA transfer
size in sync. Tail probability at 840 bytes: well below 2⁻¹⁰⁰⁰ per call.
The host reference and the transliteration cross-check tool are updated to
draw 840 SHAKE128 bytes as well.

This means **M32c must be re-dispatched on the laptop** to pick up the new
`XOF_MAX_OUT`; the existing M32c gates should still all PASS (their inputs are
short, so the extra buffer capacity is unused).

The theoretical analysis of SampleNTT tail behavior (including the notion of
"unlucky vectors" that exercise the tail) is documented in the community
project [CCTV (C2SP CryptoCharTestVectors)](https://github.com/C2SP/CCTV/blob/main/ML-KEM/README.md)
and in Filippo Valsorda's [mlkem768 blog post](https://words.filippo.io/mlkem768/).

## NTT convention and the Montgomery bridge

The host reference (`mlkem_composer.HostBackend`, matching
[kyber-py](https://github.com/GiacomoPope/kyber-py/blob/main/src/kyber_py/polynomials/polynomials.py))
uses **positive residues in `[0, q)`** and the FIPS 203 zetas table
`zetas[i] = 17^{br(i, 7)} mod q`. `zeta = 17` is the primitive 256th root of
unity mod `q = 3329`. Base-case multiplication follows FIPS 203 Algorithm 12:
`(a0 + a1·X) · (b0 + b1·X) mod (X² − γ)` with `γ = zetas[64 + i]` for the first
two coefficients of each length-4 subblock and `γ = q − zetas[64 + i]` for the
other two.

M32b silicon, however, is a **line-for-line transliteration of pq-crystals**
(`ref/ntt.c`, `ref/reduce.c`). Its ZETAS table is pre-multiplied by
`R = 2^16 mod q` and every zeta-use is wrapped in `fqmul = montgomery_reduce`.
Working the algebra out for each primitive on plain positive-residue inputs:

| Primitive | Silicon output (relative to true plain value) |
| --- | --- |
| `ntt(f)` | `ntt_true(f) mod q` (R cancels via Montgomery-scaled ZETAS) |
| `intt(x)` | `R * invntt_true(x) mod q` (one residual R factor) |
| `basemul(a, b)` | `(a * b) * R^{-1} mod q` (one residual R^{-1}) |
| `poly_add / poly_sub` | plain (Z_q-linear, no residual) |

Round-trip identity `silicon.intt(silicon.ntt(f)) == R * f mod q` is asserted
by M32b gate (a). It confirms the two residual factors above.

Since M32b is off-limits to modify (its own gates already pass on silicon),
`SiliconBackend` in `test_mlkem_m32e.py` performs a **Python-side convention
bridge**:

* `ntt` output is reduced with `int(c) % q`.  The raw pq-crystals `ntt` output
  can sit anywhere in `(-2q, 2q)` (no barrett reduction inside the butterfly),
  and `poly_tobytes_d12` (M32d MODE 4) only applies a single conditional
  add-q via `t += (t>>15) & q`, which is insufficient to bring `(-2q, -q]`
  values back into `[0, q)`.  KeyGen publishes `s_hat` bytes directly with no
  intervening `poly_add` (which would apply a barrett reduction), so an
  explicit Python-side `% q` is required here.  Encaps/decaps happen to hide
  the same issue because every intermediate result flows through `poly_add`
  or `poly_sub` before `poly_tobytes_d12`.
* `intt` output is multiplied by `R^{-1} = 169 mod q` (strips the residual R).
* `basemul` output is multiplied by `R = 2285 mod q` and reduced (strips the
  residual R^{-1} and normalises to `[0, q)`).

This makes every silicon primitive appear as a pure plain-residue operator to
the composer.

The encapsulation chain
`intt(basemul(ntt(a), ntt(b))) → plain time-domain (a * b)` then holds because
the two applied compensations (`× R^{-1}` on intt, `× R` on basemul) cancel
exactly against the residual factors, matching the FIPS 203 identity.

This bridge existed implicitly in the earlier (buggy) run: silicon encaps
passed 25/25 because the raw `R^{-1}` from basemul cancelled the raw `R` from
intt end-to-end. Silicon KeyGen failed because it publishes
`t_hat = A · s_hat + e_hat` mid-chain, where the residual R^{-1} on the
matrix product term was left uncompensated. The explicit bridge above makes
both paths correct.

References:
[pq-crystals ref/reduce.c](https://github.com/pq-crystals/kyber/blob/main/ref/reduce.c),
[pq-crystals ref/ntt.c](https://github.com/pq-crystals/kyber/blob/main/ref/ntt.c),
[FIPS 203 Algs 9/10/12](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf).

## Test procedure

**Sandbox (reference-only, no silicon):**

```bash
cd C:\phoenix-sdr-dsp
python -m pytest tests/m32_mlkem/test_mlkem_m32e.py -v
python tools/m32e_kernel_transliteration_check.py
```

Expected: 60 reference gates PASS, 9 silicon gates SKIP; cross-check reports
60 PASS, 0 FAIL.

**Laptop silicon smoke (default: 3 KATs per axis = 9 silicon gates):**

Prerequisite — re-dispatch **M32c** to pick up the XOF budget bump; existing
gates should still PASS:

```bash
cd C:\phoenix-sdr-dsp
python tests\m32_mlkem\test_keccak_shake_m32c.py
python tests\m32_mlkem\test_mlkem_m32e.py
```

Expected: M32c 12/12 (or however many gates it now reports) PASS;
M32e 60 reference + 9 silicon = 69 PASS.

**Laptop silicon full sweep (60 KATs on silicon):**

```bash
set M32E_FULL_KAT=1
python tests\m32_mlkem\test_mlkem_m32e.py
```

Runtime: roughly 60 * (30..70) = 1800..4200 DMA round-trips per KAT set.

## Milestone bump

M32e is the fifth Track-4 (PQC) milestone landed:

- M32b (NTT): SILICON PASS 5/5
- M32c (Keccak / SHAKE / samplers): SILICON PASS 12/12 (will re-run after XOF bump)
- M32d (K-PKE byte layer): SILICON PASS 8/8
- **M32e (ML-KEM-512 composition): pending SILICON PASS on laptop**

Contract path (per project instruction, versions not bumped until user says so):
24/24 → 25/25 (M27) → 26/26 (M32c) → 27/27 (M32b) → 28/28 (M32d) → **29/29 (M32e)**.

## References

- FIPS 203 — Module-Lattice-Based Key-Encapsulation Mechanism Standard, NIST (Aug 2024). [https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)
- FIPS 203 landing / metadata. [https://csrc.nist.gov/pubs/fips/203/final](https://csrc.nist.gov/pubs/fips/203/final)
- NIST ACVP-Server test vector repository. [https://github.com/usnistgov/ACVP-Server](https://github.com/usnistgov/ACVP-Server)
- ACVP ML-KEM keyGen vectors. [https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files/ML-KEM-keyGen-FIPS203](https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files/ML-KEM-keyGen-FIPS203)
- ACVP ML-KEM encapDecap vectors. [https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files/ML-KEM-encapDecap-FIPS203](https://github.com/usnistgov/ACVP-Server/tree/master/gen-val/json-files/ML-KEM-encapDecap-FIPS203)
- pq-crystals/kyber reference C implementation. [https://github.com/pq-crystals/kyber/tree/main/ref](https://github.com/pq-crystals/kyber/tree/main/ref)
- kyber-py — independent Python ML-KEM implementation (used as second-source oracle). [https://pypi.org/project/kyber-py/](https://pypi.org/project/kyber-py/), source at [https://github.com/GiacomoPope/kyber-py](https://github.com/GiacomoPope/kyber-py)
- CRYSTALS-Kyber round-3 specification. [https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf)
- C2SP CCTV — ML-KEM community test-vector notes (unlucky vectors, tail probability). [https://github.com/C2SP/CCTV/blob/main/ML-KEM/README.md](https://github.com/C2SP/CCTV/blob/main/ML-KEM/README.md)
- Filippo Valsorda — mlkem768 in Go, article on ML-KEM implementation subtleties. [https://words.filippo.io/mlkem768/](https://words.filippo.io/mlkem768/)
- AMD Ryzen AI (Phoenix NPU / AIE2) hardware overview. [https://www.amd.com/en/products/processors/consumer/ryzen-ai.html](https://www.amd.com/en/products/processors/consumer/ryzen-ai.html)
- MLIR-AIE (IRON API) — programming model used for M32b/c/d/e kernels. [https://github.com/Xilinx/mlir-aie](https://github.com/Xilinx/mlir-aie)
