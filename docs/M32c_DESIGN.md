# M32c — Post-Quantum Cryptography Foundations: SHA-3 / SHAKE (FIPS 202) + SamplePolyCBD + SampleNTT on AIE2

**Status:** ⏸️ In bring-up (kernel written, awaiting silicon PASS on laptop)
**Track:** 4 — Post-Quantum Cryptography (PQC) on NPU
**Depends on:** M22/M23/M26/M27 kernel discipline (single-tile AIE2, `@iron.jit`, 2 in-fifos + 1 out-fifo, program-memory-conscious inner loops)
**Deliverables:** `tests/m32_mlkem/keccak_shake_kernel.cc`, `tests/m32_mlkem/test_keccak_shake_m32c.py`, `tools/m32c_kernel_transliteration_check.py`, this document.

---

## 1. Purpose and PQC context

M32c is the first milestone on **Track 4 — Post-Quantum Cryptography on NPU**. Track 4 targets the Ryzen AI Phoenix NPU (AIE2, five columns by four compute-tile rows) as an accelerator for post-quantum cryptographic primitives. Post-quantum cryptography is the family of public-key algorithms designed to resist attack by a large-scale quantum computer running Shor's algorithm ([Shor 1994](https://ieeexplore.ieee.org/document/365700)); NIST ran a multi-year standardization process from 2016 to 2024 to select algorithms for federal use ([NIST PQC Project](https://csrc.nist.gov/projects/post-quantum-cryptography)), and the first three finalized standards were published in August 2024 ([NIST press release 2024-08-13](https://www.nist.gov/news-events/news/2024/08/nist-releases-first-3-finalized-post-quantum-encryption-standards)):

- **FIPS 203 — Module-Lattice-based Key-Encapsulation Mechanism (ML-KEM)**, derived from CRYSTALS-Kyber ([FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf))
- **FIPS 204 — Module-Lattice-based Digital Signature Algorithm (ML-DSA)**, derived from CRYSTALS-Dilithium ([FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf))
- **FIPS 205 — Stateless Hash-Based Digital Signature Algorithm (SLH-DSA)**, derived from SPHINCS+ ([FIPS 205](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.205.pdf))

Track 4 focuses first on **ML-KEM** (FIPS 203) because it is the primary post-quantum key-exchange primitive intended to replace ECDH / X25519 in TLS 1.3, IKEv2, SSH, Signal, and hybrid handshakes ([IETF hybrid design](https://datatracker.ietf.org/doc/draft-ietf-tls-hybrid-design/), [Kwiatkowski et al 2024](https://blog.cloudflare.com/pq-2024/)). Downstream milestones (M32b/d/e) build the NTT-domain arithmetic, K-PKE component, and full ML-KEM-512 KeyGen/Encaps/Decaps on top of the primitives delivered here.

**M32c specifically delivers the three PQC building blocks that every operation in ML-KEM depends on:**

1. The **Keccak-*f*[1600] permutation** and the four FIPS 202 sponge instantiations it drives — SHAKE128, SHAKE256, SHA3-256, SHA3-512 — implemented as one fused single-tile AIE2 kernel ([FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf)).
2. **SampleNTT** — rejection sampling of the SHAKE128 XOF stream to produce a uniform ring element `â ∈ R_q` (FIPS 203 Algorithm 7).
3. **SamplePolyCBDη** — the centered binomial distribution sampler with η ∈ {2, 3}, driven by a PRF (SHAKE256) output (FIPS 203 Algorithm 8).

All three are the *only* sources of randomness inside ML-KEM key generation and encapsulation, so they must be bit-exact against the FIPS 202 / FIPS 203 test vectors before any of the M32b–M32e milestones can be trusted.

## 2. Mathematical background

### 2.1 The Keccak-*f*[1600] permutation

FIPS 202 §3.1 defines the Keccak-*p* family and fixes SHA-3 / SHAKE to use Keccak-*f*[1600] = Keccak-*p*[1600, 24] ([FIPS 202 §5.2](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf)). The permutation state is a 5 × 5 × 64-bit array

$$A : \{0,1,2,3,4\} \times \{0,1,2,3,4\} \times \{0,1,\dots,63\} \to \{0,1\}$$

stored as 25 lanes of 64 bits each, with `lane(x,y) = A[x,y,·]` treated as a little-endian 64-bit word ([Keccak specifications summary](https://keccak.team/keccak_specs_summary.html)). One round applies five step mappings θ, ρ, π, χ, ι in sequence; Keccak-*f*[1600] applies 24 rounds:

- **θ step** — column parity diffusion. For each x, C[x] = A[x,0] ⊕ A[x,1] ⊕ A[x,2] ⊕ A[x,3] ⊕ A[x,4]; then D[x] = C[x−1] ⊕ ROL64(C[x+1], 1); then A[x,y] ← A[x,y] ⊕ D[x].
- **ρ step** — per-lane bitwise cyclic rotation by fixed offsets r[x,y] given in FIPS 202 §3.2.2 (equivalent to (t+1)(t+2)/2 mod 64 along a 24-step orbit starting at (1,0)).
- **π step** — lane permutation B[y, 2x+3y] = A[x,y].
- **χ step** — the only nonlinear step. Within each row y, A[x,y] ← B[x,y] ⊕ ((¬B[x+1,y]) ∧ B[x+2,y]).
- **ι step** — XOR a round-specific constant RC[i] into lane (0,0). RC[i] is the 64-bit truncation of an 8-bit LFSR sequence with primitive polynomial x⁸ + x⁶ + x⁵ + x⁴ + 1 ([Keccak reference 3.0 §1.2](https://keccak.team/files/Keccak-reference-3.0.pdf)).

The 24 round constants and the 25 rotation offsets are fixed by the standard and reproduced in [Keccak specifications summary Table 1 & 2](https://keccak.team/keccak_specs_summary.html). Our reference implementation matches the XKCP compact reference ([XKCP Keccak-readable-and-compact.c](https://github.com/XKCP/XKCP/blob/master/Standalone/CompactFIPS202/C/Keccak-readable-and-compact.c)) which computes both tables on-the-fly from the LFSR (RC) and the (t+1)(t+2)/2 recurrence (ρ), avoiding any large lookup tables in `.rodata`.

### 2.2 Sponge construction and the four FIPS 202 modes

The sponge construction ([Bertoni et al 2007](https://keccak.team/files/CSF-0.1.pdf)) turns a permutation into an extendable-output function by partitioning the 1600-bit state into a rate portion of `r` bits and a capacity portion of `c = 1600 − r` bits. The input is absorbed r bits at a time (each block XORed into the rate lanes, then one Keccak-*f*[1600] applied); after the final block is padded, output is squeezed r bits at a time. FIPS 202 §5.1 specifies the multi-rate padding rule pad10*1: append the domain-separation suffix `dsp` (a 2-bit or 4-bit tag identifying which mode), then a 1 bit, then zero or more 0 bits, then a final 1 bit, filling to a multiple of r. The four instantiations we implement:

| Mode | r (bits) | r (bytes) | c (bits) | dsp | Output |
|---|---|---|---|---|---|
| SHAKE128 | 1344 | 168 | 256 | 0x1F | XOF, any length |
| SHAKE256 | 1088 | 136 | 512 | 0x1F | XOF, any length |
| SHA3-256 | 1088 | 136 | 512 | 0x06 | 32 bytes |
| SHA3-512 | 576  | 72  | 1024 | 0x06 | 64 bytes |

(The `dsp` byte encodes both the SHA-3 vs SHAKE domain separation tag and the leading 1 bit of pad10*1 in a single byte, as documented in the XKCP compact reference header comment.)

### 2.3 Instantiation inside FIPS 203 ML-KEM

FIPS 203 §4.1 fixes the four PQC-usage names of the FIPS 202 modes ([FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)):

- **XOF(seed)** = SHAKE128(seed). Driver for SampleNTT (§4.2.2 Alg 7).
- **H(x)** = SHA3-256(x). Used to derive the public-key hash and to bind the message.
- **G(x)** = SHA3-512(x). Used to expand seeds into (ρ, σ) pairs.
- **PRF(η, s, b)** = SHAKE256(s ‖ b). Driver for SamplePolyCBDη (§4.2.2 Alg 8), where η ∈ {2, 3}.
- **J(x)** = SHAKE256(x, 32). Implicit-rejection tag used in Decaps.

M32c exposes the FIPS 202 primitives above and lets higher-level milestones
name them XOF / H / G / PRF / J at the call site. Use the final FIPS 203
function names at the implementation boundary; do not introduce a separate
`KDF` label unless it is explicitly mapped to the applicable standard step.

### 2.4 SampleNTT (FIPS 203 Algorithm 7)

`SampleNTT` converts a 32-byte seed plus a 2-byte (j, i) domain-separation tag into a uniform ring element `â ∈ R_q` where `R_q = Z_q[X] / (X²⁵⁶ + 1)` and `q = 3329`. The algorithm feeds `(seed ‖ j ‖ i)` into SHAKE128 as an XOF and consumes bytes three at a time. Each 3-byte block is unpacked into two 12-bit little-endian integers

$$d_1 = b_0 + 256 (b_1 \bmod 16), \qquad d_2 = \lfloor b_1 / 16 \rfloor + 16 b_2$$and each 12-bit integer is accepted iff it is < q. With acceptance probability$p = 3329/4096$, each three-byte group supplies two independent candidates.
The expected group count to accept 256 coefficients is
$256/(2p) \approx 157.49$, or about 472.47 bytes (about 2.81 SHAKE128 rate
blocks). A conforming unbounded implementation must squeeze additional
SHAKE128 blocks until completion; a bounded research implementation must
signal its limit rather than present an incomplete polynomial as a successful
SampleNTT result. The retained M32c DMA ABI has a fixed 840-byte cap and no
limit-status field, so it is not a FIPS-conformance claim ([FIPS 203, Algorithm
7](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)).

### 2.5 SamplePolyCBDη (FIPS 203 Algorithm 8)

`SamplePolyCBDη` produces a ring element whose 256 coefficients are drawn from the centered binomial distribution CBD(η): each coefficient equals ∑ aᵢ − ∑ bᵢ where a₁ … aη and b₁ … bη are η pairs of independent uniform bits. The routine consumes exactly 64η bytes of PRF (SHAKE256) output — 128 bytes for η = 2 (ML-KEM-768/1024) or 192 bytes for η = 3 (ML-KEM-512) — and lays them out as a bit stream. Coefficient i is

$$f_i = \sum_{j=0}^{\eta-1} B[2\eta i + j] - \sum_{j=0}^{\eta-1} B[2\eta i + \eta + j]$$

where `B[·]` indexes the bit stream in little-endian byte-bit order (LSB-first within each byte). Output coefficients lie in {−η, …, +η}. For η = 2 the distribution has variance 1; for η = 3 the variance is 3/2 ([Kyber CFRG draft §2.4](https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html)).

## 3. Kernel architecture

### 3.1 Single-tile placement

The full M32c stack fits on **one AIE2 compute tile** on the Phoenix NPU 4×5 array ([Linux kernel AMD NPU documentation](https://docs.kernel.org/accel/amdxdna/amdnpu.html)). We follow the M27 topology lesson: AIE2 compute tiles have 2 input DMA channels + 2 output DMA channels; overrunning 2 in + 1 out breaks placement, so M32c uses exactly:

- `in_bytes`  — u8 buffer, absorbed message + trailing domain-separation control block
- `in_ctrl`   — u8 control block: `{mode, in_len_lo, in_len_hi, out_len_lo, out_len_hi, eta, ntt_flag, seed_j, seed_i}` (9 bytes zero-padded to 16)
- `out_bytes` — u8 buffer, hash / XOF / sampled polynomial output

The kernel dispatches on `mode ∈ {SHA3_256, SHA3_512, SHAKE128, SHAKE256, SAMPLE_NTT, SAMPLE_CBD}` and interprets `out_bytes` per mode. `SAMPLE_NTT` returns 256 × int16 coefficients (512 bytes). `SAMPLE_CBD` returns 256 × int16 coefficients centered around zero.

### 3.2 Program-memory budget (M27 lesson)

AIE2 program-memory is 16 KiB per tile. M27 hit this limit with the OFDM loopback and mitigated it via `#pragma clang loop unroll(disable)` on all counted loops and `__attribute__((noinline))` on the inner FIR routine. M32c applies the same discipline:

- The θ / ρ+π / χ inner loops of `keccak_f1600_state_permute` are `unroll(disable)`.
- `keccak_f1600_state_permute` is `noinline`; each invocation executes the 24-round permutation and must not be duplicated.
- The absorb loop, the squeeze loop, and the SampleNTT `while (accepted < 256)` loop are `unroll(disable)`.
- LFSR-based round-constant generation and the on-the-fly `(t+1)(t+2)/2 mod 64` rotation offset avoid `.rodata` tables entirely.

### 3.3 Little-endian lane load / store on AIE2

The XKCP compact reference documents a portable load64/store64/xor64 path for big-endian hosts and a direct `((uint64_t*)state)` cast for little-endian ([XKCP Keccak-readable-and-compact.c](https://github.com/XKCP/XKCP/blob/master/Standalone/CompactFIPS202/C/Keccak-readable-and-compact.c)). AIE2 is little-endian ([AMD AI Engine architecture manual AM009](https://docs.amd.com/r/en-US/am009-versal-ai-engine)), so we take the direct-cast path. The state is a 200-byte scratch buffer viewed as `uint64_t state_lanes[25]`.

### 3.4 Rotation and round-constant generation

- Rotation: `ROL64(a, r) = (a << r) | (a >> (64 − r))`, well-defined for r ∈ [1, 63]. In the ρ step orbit we compute r = ((t+1)(t+2)/2) mod 64 with a `uint32_t` accumulator refreshed each round.
- Round constants: 8-bit LFSR `LFSR86540` with polynomial 0x71 (x⁸ + x⁶ + x⁵ + x⁴ + 1), initialised to 0x01 at the start of each permutation call. Each of the 7 bit-positions `2ʲ − 1` for j ∈ [0, 6] queries one LFSR bit; if that bit is 1, XOR (1 << (2ʲ − 1)) into lane (0,0).

## 4. Silicon PASS gates

Four gates run in `test_keccak_shake_m32c.py`. Each has a matching reference test using the host bit-exact Python transliteration.

### Gate (a) — Transliteration bit-exact

`tools/m32c_kernel_transliteration_check.py` re-runs the sandbox reference Python (which matches the AIE2 C bit-for-bit at u8/u64 level) against the AIE2 output over 3 seeds × 4 modes and asserts byte-equality on every output.

### Gate (b) — FIPS 202 CAVP known-answer tests

The NIST CAVS/CAVP test vectors for SHA-3 and SHAKE ([NIST CSRC CAVP hash validation](https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/secure-hashing)) include:

- **SHA3-256 empty input**: `a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a`
- **SHA3-512 empty input**: `a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a615b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26`
- **SHAKE128 empty, 32-byte output**: `7f9c2ba4e88f827d616045507605853ed73b8093f6efbc88eb1a6eacfa66ef26`
- **SHAKE256 empty, 32-byte output**: `46b9dd2b0ba88d13233b3feb743eeb243fcd52ea62b81b82b50c27646ed5762f` (verified live against `hashlib.shake_256(b'').digest(32)`, which uses the OpenSSL SHA-3 provider validated by [NIST CSRC CAVP secure-hashing](https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/secure-hashing))

The kernel result must match byte-for-byte on all four.

### Gate (c) — SampleNTT reproducibility

Given a fixed 32-byte seed `ρ = 0x00 … 0x1F` and (j, i) = (0, 0), the resulting NTT-domain ring element `â ∈ Z_3329²⁵⁶` is deterministic. The reference model precomputes the expected 256 coefficients and the kernel must reproduce them exactly. All 256 values lie in `[0, 3328]` — hard-asserted, since the entire correctness of SampleNTT rests on the rejection-sampling < q gate.

### Gate (d) — SamplePolyCBD statistical + reproducibility

Two sub-gates for both η = 2 and η = 3:

- **Reproducibility**: Given a fixed PRF seed `s = 0x42 · 32`, byte `b = 0`, and η ∈ {2, 3}, the 256 output coefficients must match the reference exactly.
- **Statistical sanity**: Coefficient histogram over N = 4096 fresh samples (16 polynomials at η = 2, then 16 at η = 3) must match the theoretical binomial pmf within 3σ per bin. For η = 2 the pmf is (1, 4, 6, 4, 1)/16 over {−2, −1, 0, 1, 2}; for η = 3 it is (1, 6, 15, 20, 15, 6, 1)/64 over {−3, −2, −1, 0, 1, 2, 3} ([Kyber CFRG draft §2.4](https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html)).

## 5. Files

- `tests/m32_mlkem/keccak_shake_kernel.cc` — single-tile AIE2 kernel; entrypoint `keccak_shake` with signature `(const uint8_t* in_bytes, const uint8_t* in_ctrl, uint8_t* out_bytes)`.
- `tests/m32_mlkem/test_keccak_shake_m32c.py` — pytest module with the four silicon gates and their four reference-only companions (host Python bit-exact).
- `tools/m32c_kernel_transliteration_check.py` — sandbox verification tool asserting host reference ≡ kernel over 3 seeds × 4 modes.

## 6. Non-goals for M32c

- No NTT-domain arithmetic (M32b).
- No K-PKE encryption/decryption (M32d).
- No full ML-KEM-512 KeyGen/Encaps/Decaps (M32e).
- No constant-time, side-channel-resistance, or secure-zeroization claim is made. SampleNTT rejection sampling has data-dependent completion, and this research record does not evaluate leakage or fault behavior.

## 7. References

- FIPS 202 — SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions, NIST, August 2015. https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf
- FIPS 203 — Module-Lattice-Based Key-Encapsulation Mechanism Standard, NIST, August 2024. https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- FIPS 204 — Module-Lattice-Based Digital Signature Standard, NIST, August 2024. https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
- FIPS 205 — Stateless Hash-Based Digital Signature Standard, NIST, August 2024. https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.205.pdf
- NIST Post-Quantum Cryptography Project. https://csrc.nist.gov/projects/post-quantum-cryptography
- NIST press release, "NIST Releases First 3 Finalized Post-Quantum Encryption Standards", 2024-08-13. https://www.nist.gov/news-events/news/2024/08/nist-releases-first-3-finalized-post-quantum-encryption-standards
- Keccak specifications summary. https://keccak.team/keccak_specs_summary.html
- Keccak Reference 3.0. https://keccak.team/files/Keccak-reference-3.0.pdf
- Bertoni, Daemen, Peeters, Van Assche, "Sponge functions", ECRYPT Hash Workshop 2007. https://keccak.team/files/CSF-0.1.pdf
- XKCP CompactFIPS202 reference. https://github.com/XKCP/XKCP/blob/master/Standalone/CompactFIPS202/C/Keccak-readable-and-compact.c
- Kyber round-3 specification. https://pq-crystals.org/kyber/data/kyber-specification-round3-20210131.pdf
- Schwabe et al, "Kyber", CFRG Internet-Draft 04. https://www.ietf.org/archive/id/draft-cfrg-schwabe-kyber-04.html
- NIST CSRC CAVP secure-hashing validation. https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/secure-hashing
- Shor, "Algorithms for quantum computation: discrete logarithms and factoring", FOCS 1994. https://ieeexplore.ieee.org/document/365700
- Kwiatkowski et al, "The state of the post-quantum internet in 2024", Cloudflare 2024. https://blog.cloudflare.com/pq-2024/
- IETF Hybrid key-exchange in TLS 1.3 draft. https://datatracker.ietf.org/doc/draft-ietf-tls-hybrid-design/
- AMD AI Engine architecture manual AM009. https://docs.amd.com/r/en-US/am009-versal-ai-engine
