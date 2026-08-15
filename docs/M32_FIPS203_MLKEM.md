# M32 — FIPS 203 ML-KEM (planned)

Status: next NTT-track milestone. Not in `run_all_silicon_tests.py`.
No silicon claim. No KAT claim.

M10–M15b already sit on the ML-KEM ring. This milestone turns those
primitives into the approved key-encapsulation mechanism in
[NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)
(*Module-Lattice-Based Key-Encapsulation Mechanism Standard*, 13 August
2024, [DOI 10.6028/NIST.FIPS.203](https://doi.org/10.6028/NIST.FIPS.203);
[CSRC final](https://csrc.nist.gov/pubs/fips/203/final)).

FIPS 203 §1.1 states that ML-KEM is derived from the round-3
[CRYSTALS-Kyber](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf)
KEM. Differences that change KeyGen / Encaps / Decaps I/O are listed in
FIPS 203 Appendix C. Implement FIPS 203, not Kyber v3.02, when the two
disagree. Track the CSRC [errata spreadsheet](https://csrc.nist.gov/pubs/fips/203/final)
(planning note 17 November 2025).

## Why this is the next NTT item

Shipped building blocks:

| Milestone | What it already gives M32 | Gap versus FIPS 203 |
|---|---|---|
| M10 | Barrett reduction modulo `q = 3329` | Method is [Barrett, CRYPTO 1986](https://link.springer.com/chapter/10.1007/3-540-47721-7_24). FIPS 203 only requires correct reduction in `Z_q`. |
| M11 | Radix-2 NTT butterfly | Not yet wired as Algorithms 9–12. |
| M12 | CPU NTT / INTT reference | Must be checked against FIPS 203 Algorithms 9 and 10, not only the in-repo cyclic tables. |
| M13 / M14 | 16-point and 256-point NPU NTT | 256 matches `n = 256`. Need the ML-KEM bit-reversed ζ schedule (`ζ = 17`, FIPS 203 §2.3). |
| M15 | Cyclic product in `Z_q[x]/(x^{256}−1)` | ML-KEM is negacyclic (`x^n+1`), not cyclic. |
| M15b | Schoolbook product in `Z_3329[x]/(x^{256}+1)` | Correct ring ([FIPS 203 §2.3](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf); [Isabelle/AFP](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf)). Algorithm is O(N²) schoolbook, **not** the NTT product in FIPS 203 §4.3. |

M15b is therefore the ring proof, not the KEM. Do not describe M15b as
NTT-based. Do not silently replace M15b `MU = 20165` with M15's `20158`.

## Standard objects

Ring ([FIPS 203 §2.3](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)):

```text
R_q = Z_q[X] / (X^n + 1)
n   = 256
q   = 3329 = 2^8 * 13 + 1
ζ   = 17          # primitive n-th root of unity modulo q
```

Approved parameter sets ([FIPS 203 Table 2, §8](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)):

| Set | n | q | k | η1 | η2 | du | dv | Category |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| ML-KEM-512 | 256 | 3329 | 2 | 3 | 2 | 10 | 4 | 1 |
| ML-KEM-768 | 256 | 3329 | 3 | 2 | 2 | 10 | 4 | 3 |
| ML-KEM-1024 | 256 | 3329 | 4 | 2 | 2 | 11 | 5 | 5 |

NIST recommends ML-KEM-768 as the default ([FIPS 203 §8](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)).
First silicon target is ML-KEM-512 (`k = 2`) because the matrix
`A` is 2×2 instead of 3×3.

Sizes in bytes ([FIPS 203 Table 3](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)):

| Set | ek | dk | ciphertext | shared secret |
|---|---:|---:|---:|---:|
| ML-KEM-512 | 800 | 1632 | 768 | 32 |
| ML-KEM-768 | 1184 | 2400 | 1088 | 32 |
| ML-KEM-1024 | 1568 | 3168 | 1568 | 32 |

Hashes and XOFs come from [FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf)
([DOI 10.6028/NIST.FIPS.202](https://doi.org/10.6028/NIST.FIPS.202)),
instantiated as in FIPS 203 §4.1:

| Symbol | Instantiation |
|---|---|
| H | SHA3-256 |
| G | SHA3-512 → two 32-byte strings |
| J | SHAKE256(·, 256 bits) |
| PRF_η | SHAKE256(s ‖ b, 8·64·η) |
| SampleNTT XOF | SHAKE128 |

## Algorithms to implement

All names and numbers are from
[FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf).

| # | Name | Section | Role |
|---|---|---|---|
| 5 / 6 | ByteEncode_d / ByteDecode_d | §4.2.1 | Integer ↔ byte arrays |
| (4.7)/(4.8) | Compress_d / Decompress_d | §4.2.1 | Ciphertext compression |
| 7 | SampleNTT | §4.2.2 | Uniform polynomial in T_q |
| 8 | SamplePolyCBD_η | §4.2.2 | Centered binomial, η ∈ {2,3} |
| 9 / 10 | NTT / NTT⁻¹ | §4.3 | Negacyclic transform |
| 11 / 12 | MultiplyNTTs / BaseCaseMultiply | §4.3.1 | Product in T_q |
| 13–15 | K-PKE.KeyGen / Encrypt / Decrypt | §5 | Inner PKE **component only** |
| 16–18 | ML-KEM.*_internal | §6 | Deterministic CAVP interfaces |
| 19–21 | ML-KEM.KeyGen / Encaps / Decaps | §7 | Approved KEM |

FIPS 203 §3.3: K-PKE shall not be used as a stand-alone public-key
encryption scheme. Algorithms 13–15 are not approved in isolation.

## Gated build order

Do not combine unvalidated gates. Master prompt §16 / §20.

1. **M32a — CPU ML-KEM-512 reference.** Host-only Python. Bit-exact
   Algorithms 5–21 against NIST
   [example values](https://csrc.nist.gov/projects/cryptographic-standards-and-guidelines/example-values)
   and the CAVP internal interfaces in FIPS 203 §6
   ([CAVP](https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program)).
2. **M32b — NTT-domain negacyclic product on the NPU.** Algorithms 9–12
   on Phoenix NPU1, checked bit-exact against the M32a CPU NTT. This is
   the missing silicon step after M15b schoolbook.
3. **M32c — Sampling.** Host SHA3/SHAKE (FIPS 202) plus SampleNTT and
   SamplePolyCBD. NPU offload of SHAKE is optional and later.
4. **M32d — K-PKE component.** Algorithms 13–15, test-only, never
   exposed as a public API.
5. **M32e — Approved KEM.** Algorithms 19–21 for ML-KEM-512, then 768
   (NIST default), then 1024. Shared secret 32 bytes. Pass
   KeyGen / Encaps / Decaps known-answer and implicit-rejection cases.

Directory: `tests/m32_mlkem/`. Do not add it to
`run_all_silicon_tests.py` until a gate produces a bit-exact NPU result.

## Pass criteria

- CPU reference matches FIPS 203, not Kyber-round-3 where Appendix C
  lists a difference.
- NPU NTT product is bit-exact modulo 3329 against the CPU reference.
- Encaps(ek) / Decaps(dk, c) recover the same 32-byte shared secret on
  honest transcripts.
- Implicit rejection (Decaps on a malformed ciphertext) follows
  Algorithm 21, not a silent failure.
- No claim of CAVP/CMVP certification from this repo work.

## References

- NIST, FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (2024-08-13). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 203 landing page. https://csrc.nist.gov/pubs/fips/203/final
- DOI 10.6028/NIST.FIPS.203. https://doi.org/10.6028/NIST.FIPS.203
- NIST, FIPS 202, *SHA-3 Standard* (2015). https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
- NIST Post-Quantum Cryptography project. https://csrc.nist.gov/projects/post-quantum-cryptography
- NIST CAVP. https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program
- NIST cryptographic example values. https://csrc.nist.gov/projects/cryptographic-standards-and-guidelines/example-values
- Avanzi et al., *CRYSTALS-Kyber* specification v3.02 (2021-08-04). https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf
- Isabelle/AFP CRYSTALS-Kyber. https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf
- P. Barrett, CRYPTO 1986. https://link.springer.com/chapter/10.1007/3-540-47721-7_24
- `iron.Runtime` at the v1.4.1 pin. https://github.com/Xilinx/mlir-aie/blob/3ca0193/python/iron/runtime/runtime.py
