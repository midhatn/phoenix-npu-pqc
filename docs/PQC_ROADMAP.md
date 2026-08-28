# PQC Roadmap

**Document class:** Accepted design and governance roadmap for the device-resident
post-quantum cryptography DR series on AMD Phoenix NPU. The user-review
decision is recorded in Section 12.

**Status convention**

- **FROZEN / EXISTING:** An established, physically validated baseline. This
  document does not reopen or renumber it.
- **OPEN / REQUIRED FOR CLOSURE:** Work that is mandatory to close the current
  umbrella milestone.
- **PROPOSED / USER REVIEW:** A suggested future boundary and number. Inclusion
  here does not approve, authorize, or start it.
- **ACCEPTED ROADMAP BOUNDARY / NOT STARTED:** The user has approved the
  milestone definition and sequence, but implementation has not started and
  may begin only after the preceding closure gate.
- **ACCEPTED:** May be recorded only through an explicit user decision.

This roadmap defines the device-resident post-quantum cryptography DR series
for `phoenix-npu-pqc`, beginning at DR0 and continuing through complete NPU
implementation of the selected finalized NIST PQC standards. It separates
physically validated baselines, completed operation-level milestones, and
the primary FIPS 202/203/204 program. FIPS 205 and FIPS 206 are retained as
unnumbered future work. The DR series is native-only and fail-closed: no
reference fallback is permitted, and only a complete terminal result may
transfer to the CPU after dispatch.

Normative algorithm references are:

- [NIST FIPS 203, Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [NIST FIPS 202, SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [NIST FIPS 204, Module-Lattice-Based Digital Signature Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
- [NIST FIPS 205, Stateless Hash-Based Digital Signature Standard](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.205.pdf)

This roadmap does not substitute for those standards and makes no
certification claim.

## 1. Purpose and 100% NPU completion language

The DR series moves from narrow, physically proven device-resident primitives
to complete operation-level PQC graphs. A DR is complete only when its
operation graph, serialization, lifecycle cleanup, fail-closed behavior,
required validation corpus, physical evidence, closure record, and explicit
user acceptance are all complete.

A validated kernel fragment, polynomial primitive, matrix entry, row, or
subgraph does not close a higher-level operation milestone.

The current active milestone is **DR6** (`ML-KEM.Encaps`). DR0 through DR5 are
**COMPLETE / PHYSICALLY VALIDATED** on AMD Phoenix NPU silicon. DR6 through
DR15 are **ACCEPTED ROADMAP BOUNDARIES** and are governed by the sequential
closure gates defined in this document.

### 1.1 Definition of 100% PQC implementation on the NPU

For every in-scope approved operation and parameter set, the NPU performs every
cryptographic transformation after raw ingress and before terminal egress.
This includes entropy conditioning and use, sampling, hashing and XOF work,
sponge/permutation processing, rejection processing, arithmetic, NTT/INTT,
encoding/decoding, compression/decompression, comparisons, selection, implicit
rejection, and signature, key, ciphertext, and shared-secret assembly.

The host may configure DMA, submit descriptors, provide raw externally sourced
bytes, and receive declared terminal records. The CPU may not perform a
cryptographic transformation, sampling, hashing, encoding, comparison,
selection, re-encryption, rejection decision, assembly, reference fallback, or
intermediate continuation for an NPU-dispatched operation.

The primary 100% program comprises:

- Complete FIPS 202 on the NPU: SHA3-224, SHA3-256, SHA3-384, SHA3-512,
  SHAKE128, and SHAKE256.
- Complete FIPS 203 on the NPU: ML-KEM-512, ML-KEM-768, and ML-KEM-1024
  `KeyGen`, `Encaps`, and `Decaps`, including their internal dependencies.
- Complete FIPS 204 on the NPU: ML-DSA-44, ML-DSA-65, and ML-DSA-87
  `KeyGen`, `Sign`, and `Verify`, including approved pure/prehash interfaces
  and deterministic/hedged signing behavior where applicable.

FIPS 205 and FIPS 206 are future work. Neither has a DR number or an
implementation authorization in this roadmap. Adding either standard requires
a separate explicit user-approved roadmap revision. FIPS 205 is finalized;
FIPS 206 remains under development.

## 2. Existing baselines and completed milestones

| ID | Status | Established boundary | Evidence and claim boundary |
|---|---|---|---|
| DR0 | FROZEN / EXISTING | One fixed fused ML-DSA ring product. | Physically validated (24/24). Does not imply ML-DSA operation-level residency. |
| DR1 | FROZEN / EXISTING | One ML-DSA-44 `ExpandA` / `RejNTT` polynomial. | Physically validated (33/33). Does not imply a complete ML-DSA graph. |
| DR2a | FROZEN / EXISTING | One bounded ML-KEM-512 `SampleNTT` polynomial. | Physically validated (13/13). DR2 constituent. |
| DR2b | FROZEN / EXISTING | One ML-KEM-512 eta1 noise-to-NTT polynomial. | Physically validated (13/13). DR2 constituent. |
| DR2c | FROZEN / EXISTING | One terminal ML-KEM-512 `K-PKE.KeyGen` $\widehat{t}$ row. | Physically validated (11/11). DR2 constituent. |
| DR2d | COMPLETE / PHYSICALLY VALIDATED | Complete device-resident ML-KEM-512 `K-PKE.KeyGen`. | **25/25 ACVP PASS on Phoenix silicon.** Closes DR2. |
| DR2 | COMPLETE / PHYSICALLY VALIDATED | Complete ML-KEM-512 `K-PKE.KeyGen` umbrella. | Closed by DR2d physical validation on 2026-08-28. |
| DR3 | COMPLETE / PHYSICALLY VALIDATED | Complete device-resident ML-KEM-512 `K-PKE.Encrypt`. | **25/25 ACVP PASS on Phoenix silicon.** 5-worker AIE2 graph. |
| DR4 | COMPLETE / PHYSICALLY VALIDATED | Complete device-resident ML-KEM-512 `K-PKE.Decrypt`. | **25/25 ACVP PASS on Phoenix silicon.** 2-worker AIE2 graph. |
| DR5 | COMPLETE / PHYSICALLY VALIDATED | Complete device-resident ML-KEM-512 `ML-KEM.KeyGen`. | **25/25 ACVP PASS on Phoenix silicon.** 6-worker AIE2 graph. |

The existing design and physical records remain authoritative for the details
of each completed milestone. This roadmap records their place in the
dependency chain without widening their claims.

## 3. Milestone sequence

```text
COMPLETE: DR0
    |
    v
COMPLETE: DR1
    |
    v
COMPLETE: DR2a -> DR2b -> DR2c -> DR2d
Complete K-PKE.KeyGen and close DR2 (100% Silicon Validated)
    |
    v
COMPLETE: DR3
Complete K-PKE.Encrypt (100% Silicon Validated)
    |
    v
COMPLETE: DR4
Complete K-PKE.Decrypt (100% Silicon Validated)
    |
    v
COMPLETE: DR5
Complete ML-KEM.KeyGen (100% Silicon Validated)
    |
    v
NEXT ACTIVE: DR6
Complete ML-KEM.Encaps
    |
    v
ACCEPTED: DR7
Complete ML-KEM.Decaps and ML-KEM-512 closure
    |
    v
ACCEPTED: DR8
Complete FIPS 203 for ML-KEM-512/768/1024
    |
    v
ACCEPTED: DR9
Complete reusable FIPS 202 NPU service
    |
    v
ACCEPTED: DR10
Entropy/key-source architecture and sealed lifecycle
    |
    v
ACCEPTED: DR11 -> DR12 -> DR13
ML-DSA-44 KeyGen -> Sign -> Verify
    |
    v
ACCEPTED: DR14
Complete ML-DSA-65
    |
    v
ACCEPTED: DR15
Complete ML-DSA-87 and primary FIPS 202/203/204 closure
```

This is the execution and publication sequence. Some later operations reuse
more than one earlier dependency, but no DR work overlaps a closure gate. The
next DR begins only after the current DR is fully validated, its closure record
is accepted by the user, and the completed DR is pushed.

FIPS 205 and FIPS 206 have no DR assignments. FIPS 205 remains finalized
future work, and FIPS 206 remains future work while under development. Final
publication or availability does not automatically add either to the active
roadmap; a separate explicit user-approved revision is required.

## 4. DR2 completion record (CLOSED & SILICON VALIDATED)

### 4.1 DR2 closure statement

**Status:** **CLOSED & PHYSICALLY VALIDATED ON PHOENIX SILICON (2026-08-28).**
DR2 closed with the physical silicon validation of **DR2d (ML-KEM-512 K-PKE.KeyGen)**.
All 25 official NIST ACVP test cases executed on the physical AMD Phoenix NPU (Ryzen 9 7940HS w/ AIE2 4-column array) with 100% bit-exact compliance, zero host CPU intermediate offload, and zero fallback.

Detailed physical evidence: [`docs/PQC_DR2D_SILICON_VALIDATION_20260828.md`](PQC_DR2D_SILICON_VALIDATION_20260828.md).

### 4.2 DR2d validated boundary

| Contract area | Verified DR2d closure condition |
|---|---|
| Designation | `DR2d` is the completed increment that closed DR2 on 2026-08-28. |
| Public ingress | `d[32]` and a descriptor, using exactly two host fills. Zero intermediate fills. |
| Device derivation | Compute `G(d || k)` entirely on device on Tile (0, 2) (`k = 2` for ML-KEM-512). Neither `rho` nor `sigma` is derived or visible on host CPU. |
| Matrix generation | Generate all four \(\widehat{A}[i,j]\) matrix polynomials for both ML-KEM-512 rows on device via Workers W1 and W3 (`SampleNTT`). |
| Noise generation | Generate and transform \(\widehat{s}[0]\), \(\widehat{s}[1]\), \(\widehat{e}[0]\), and \(\widehat{e}[1]\) on device via Worker W0 (`sample_one_nonce`). |
| Core computation | Compute both terminal \(\widehat{t}\) rows using complete matrix-vector accumulation across Workers W2 and W4. |
| Terminal serialization | Encode and assemble `ekPKE` (800 B) and `dkPKE` (768 B) into one terminal record via Worker W5. |
| Host visibility | The packed terminal key record (1,588 B) is the only result transferred to CPU after dispatch. |
| Private intermediates | All seeds derived by `G`, noise material, secret polynomials, matrix entries, products, accumulators, and serialization scratch remain strictly in internal ObjectFIFOs (`dr2d_secret_token`, `dr2d_row0_matrix`, `dr2d_row_state`, `dr2d_row1_matrix`, `dr2d_final_token`). |
| Lifecycle behavior | Explicit zeroization of secret tokens, inputs, and buffers upon completion or failure. |
| Failure behavior | Fail closed on invalid public input, descriptor error, bounded sampling failure, token corruption, or DMA failure. Zero reference fallback. |
| Validation corpus | **25 / 25 PASS** across the official NIST ACVP ML-KEM-512 KeyGen corpus on physical silicon. |
| Physical evidence | Retained in [`docs/PQC_DR2D_SILICON_VALIDATION_20260828.md`](PQC_DR2D_SILICON_VALIDATION_20260828.md). |

## 4a. DR3 completion record (CLOSED & SILICON VALIDATED)

### 4a.1 DR3 closure statement

**Status:** **CLOSED & PHYSICALLY VALIDATED ON PHOENIX SILICON (2026-08-28).**
DR3 closed with the physical silicon validation of **complete ML-KEM-512 K-PKE.Encrypt**.
All 25 official NIST ACVP test cases executed on the physical AMD Phoenix NPU with 100%
bit-exact compliance, zero host CPU intermediate offload, and zero fallback.

Detailed physical evidence: [`docs/PQC_DR3_SILICON_VALIDATION_20260828.md`](PQC_DR3_SILICON_VALIDATION_20260828.md).
Design record: [`docs/PQC_DR3_DESIGN.md`](PQC_DR3_DESIGN.md).

### 4a.2 DR3 validated boundary

| Contract area | Verified DR3 closure condition |
|---|---|
| Designation | `DR3` closed on 2026-08-28. |
| Public ingress | `ekPKE` (800 B), `m` (32 B), and `r` (32 B) packed into one request, plus one descriptor; exactly two host fills. |
| Terminal output | Serialized ciphertext `c` (768 B) is terminal-only. |
| Device residency | Key decoding, matrix expansion via `SampleNTT`, noise sampling (CBD2), NTT/INTT, matrix-vector products, additions, Compress10/Compress4, encoding, and Decompress1(m) all execute on device. |
| Prohibited paths | No intermediate CPU transfer, host-completed phase, or reference fallback. |
| Architecture | 5-worker AIE2 dataflow graph across Row 2, Cols 0-4. |
| Validation corpus | **25 / 25 PASS** across the official NIST ACVP ML-KEM-512 Encrypt corpus on physical silicon. |
| Physical evidence | Retained in [`docs/PQC_DR3_SILICON_VALIDATION_20260828.md`](PQC_DR3_SILICON_VALIDATION_20260828.md). |

## 4b. DR4 completion record (CLOSED & SILICON VALIDATED)

### 4b.1 DR4 closure statement

**Status:** **CLOSED & PHYSICALLY VALIDATED ON PHOENIX SILICON (2026-08-28).**
DR4 closed with the physical silicon validation of **complete ML-KEM-512 K-PKE.Decrypt**.
All 25 official NIST ACVP test cases executed on the physical AMD Phoenix NPU with 100%
bit-exact compliance, zero host CPU intermediate offload, and zero fallback.

Detailed physical evidence: [`docs/PQC_DR4_SILICON_VALIDATION_20260828.md`](PQC_DR4_SILICON_VALIDATION_20260828.md).
Design record: [`docs/PQC_DR4_DESIGN.md`](PQC_DR4_DESIGN.md).

### 4b.2 DR4 validated boundary

| Contract area | Verified DR4 closure condition |
|---|---|
| Designation | `DR4` closed on 2026-08-28. |
| Public ingress | `dkPKE` (768 B) and `c` (768 B) packed into one request, plus one descriptor; exactly two host fills. |
| Terminal output | Message `m` (32 B) is terminal-only. |
| Device residency | Decode ByteDecode12(dkPKE), decompress Decompress10(u) and Decompress4(v), forward NTT, pointwise inner product (MultiplyNTTs with conjugate twiddle roots), inverse NTT, modular subtraction $v - w \pmod{q}$, 1-bit threshold compression Compress1, and message encoding all execute on device. |
| Prohibited paths | No intermediate CPU transfer, host-completed phase, or reference fallback. |
| Architecture | 2-worker AIE2 dataflow graph across Row 2, Cols 0-1. Worker W0: decompress and NTT. Worker W1: inner product, INTT, subtraction, compress, CRC32, serialize. |
| Microarchitectural invariants | 32-bit aligned polynomial arrays in inter-tile DecompressToken (5136 B) to bypass AIE2 `lda.u16` index-doubling hazard. Dual-pair BaseMul with FIPS 203 conjugate twiddle roots ($+\gamma$, $q - \gamma$). |
| Validation corpus | **25 / 25 PASS** across the official NIST ACVP ML-KEM-512 Decrypt corpus on physical silicon. |
| Physical evidence | Retained in [`docs/PQC_DR4_SILICON_VALIDATION_20260828.md`](PQC_DR4_SILICON_VALIDATION_20260828.md). |

## 4c. DR5 completion record (CLOSED & SILICON VALIDATED)

### 4c.1 DR5 closure statement

**Status:** **CLOSED & PHYSICALLY VALIDATED ON PHOENIX SILICON (2026-08-28).**
DR5 closed with the physical silicon validation of **complete ML-KEM-512 ML-KEM.KeyGen**.
All 25 official NIST ACVP test cases executed on the physical AMD Phoenix NPU with 100%
bit-exact compliance, zero host CPU intermediate offload, and zero fallback.

Detailed physical evidence: [`docs/PQC_DR5_SILICON_VALIDATION_20260828.md`](PQC_DR5_SILICON_VALIDATION_20260828.md).
Design record: [`docs/PQC_DR5_DESIGN.md`](PQC_DR5_DESIGN.md).

### 4c.2 DR5 validated boundary

| Contract area | Verified DR5 closure condition |
|---|---|
| Designation | `DR5` closed on 2026-08-28. |
| Public ingress | `d[32]` and `z[32]` packed into one request (64 B), plus one descriptor (16 B); exactly two host fills. |
| Terminal output | One packed terminal record containing `ek` (800 B) and `dk` (1632 B) plus 20-byte header (total 2452 B). |
| Device residency | $G(d \parallel 2)$ derived on-device via SHA3-512; matrix $\widehat{\mathbf{A}}$ expanded via `SampleNTT`; noise sampled via $\text{CBD}_3$ and forward NTT; $\widehat{\mathbf{t}} = \widehat{\mathbf{A}} \circ \widehat{\mathbf{s}} + \widehat{\mathbf{e}} \pmod{q}$ computed on-device; $ek$ encoded; $H(ek) = \text{SHA3-256}(ek)$ computed strictly on-chip; $dk = dk_{PKE} \parallel ek \parallel H(ek) \parallel z$ packed on-chip; CRC32 calculated on-chip. |
| Prohibited paths | No intermediate CPU transfer, host-completed phase, or reference fallback. |
| Architecture | 6-worker AIE2 dataflow graph across Row 2, Cols 0-5. |
| Validation corpus | **25 / 25 PASS** across the official NIST ACVP ML-KEM-512 KeyGen corpus on physical silicon. |
| Physical evidence | Retained in [`docs/PQC_DR5_SILICON_VALIDATION_20260828.md`](PQC_DR5_SILICON_VALIDATION_20260828.md). |

## 5. Accepted future milestone boundaries

DR6 through DR7 are accepted roadmap boundaries. They do not authorize early
implementation, branch creation, publication, performance claims, security
claims, or certification claims. Each remains not started until its
predecessor's closure record, user acceptance, and required push are complete.

| ID | Proposed operation | Public ingress | Terminal-only output | Required device-resident scope | Closure focus |
|---|---|---|---|---|---|
| DR6 | ML-KEM-512 `ML-KEM.Encaps` | One packed request containing `ek` (800 B) and deterministic 32-byte test randomness, plus one descriptor; exactly two fills. | One terminal record containing `c` (768 B) and `K` (32 B). | Perform required `H`, `G`, KDF, and device `K-PKE.Encrypt` work. | Applicable ACVP encapsulation cases, deterministic reproducibility, zeroization, and physical evidence. |
| DR7 | ML-KEM-512 `ML-KEM.Decaps` and end-to-end closure | One packed request containing `dk` (1632 B) and `c` (768 B), plus one descriptor; exactly two fills. | Shared secret `K` (32 B) only. | Perform decrypt, re-encrypt, constant-shape comparison/select, implicit rejection, and KDF on device. | Applicable ACVP decapsulation cases, mutation tests, rejection-oracle review, integrated lifecycle, and full physical evidence. |

### 5.1 DR6 proposed contract

DR6 implements complete device-resident ML-KEM-512 `ML-KEM.Encaps`.

- **Input boundary:** A packed request carries `ek` (800 B) and a deterministic
  32-byte randomness/test input. A second ingress carries the descriptor.
- **Output boundary:** One terminal record carries `c` (768 B) and `K` (32 B).
- **Residency:** Required `H`, `G`, KDF, and accepted device `K-PKE.Encrypt`
  computation remain on device.
- **Randomness boundary:** The explicit 32-byte value provides deterministic
  validation. It does not define or approve a production entropy architecture.
- **Prohibited paths:** No CPU hash/KDF completion, intermediate drain, or
  reference fallback.
- **Acceptance:** All applicable vendored ACVP encapsulation cases,
  byte-exact `c` and `K`, lifecycle tests, repeated silicon runs, and physical
  evidence.

### 5.2 DR7 proposed contract

DR7 implements complete device-resident ML-KEM-512 `ML-KEM.Decaps` and closes
the proposed end-to-end ML-KEM-512 residency program.

- **Input boundary:** A packed request carries `dk` (1632 B) and `c` (768 B).
  A second ingress carries the descriptor.
- **Output boundary:** Only `K` (32 B) is terminal.
- **Residency:** Decrypt, re-encrypt, ciphertext comparison, implicit-rejection
  selection, and KDF remain on device.
- **Rejection behavior:** No status, timing distinction, payload, data path, or
  secondary output may act as a rejection oracle.
- **Integrated validation:** Applicable vendored ACVP decapsulation cases plus
  deterministic valid-ciphertext, mutated-ciphertext, mutated-key, repetition,
  and cross-operation KeyGen-to-Encaps-to-Decaps tests.
- **Physical closure:** Repeated native execution plus placement, stack, FIFO,
  DMA, shim allocation, xclbin/PDI, and worker-section evidence.
- **Prohibited paths:** No CPU comparison, selection, KDF, implicit-rejection
  decision, intermediate drain, or reference fallback.

## 6. Full PQC extension

DR8 through DR15 are accepted roadmap boundaries for completing the primary
FIPS 202/203/204 NPU program. Each remains not started until its predecessor's
closure gate is complete. FIPS 205 and FIPS 206 remain unnumbered future work
outside the active DR implementation sequence.

| ID | Proposed boundary | Required NPU-resident scope | Closure requirement |
|---|---|---|---|
| DR8 | Complete FIPS 203 across all parameter sets. | ML-KEM-512, ML-KEM-768, and ML-KEM-1024 `KeyGen`, `Encaps`, and `Decaps`; all K-PKE dependencies, sampling, hashing, codecs, comparisons, selection, implicit rejection, and serialization. | Parameter-set ACVP and operation-level evidence for all three sets; no CPU cryptographic work or intermediate drain. |
| DR9 | Complete reusable FIPS 202 NPU service. | SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, and SHAKE256; Keccak-f[1600], domain suffixes, padding, absorb, squeeze, and variable-length output behavior. | Standard vectors for all six functions plus integration evidence from consuming PQC operations; no host hashing/XOF continuation. |
| DR10 | Entropy/key-source and sealed-lifecycle architecture. | External raw ingress, NPU-native entropy, authenticated external key material including QKD ingress, provenance, domain separation, freshness/replay handling, health/error behavior, and sealed inter-operation state. | Every source mode and failure path passes; sealed chains expose no host-visible private intermediate. |
| DR11 | Complete ML-DSA-44 `KeyGen`. | All FIPS 202 use, matrix expansion, sampling, arithmetic, rounding, encoding, and public/private key assembly on the NPU. | Applicable ML-DSA-44 KeyGen ACVP/vector coverage, lifecycle evidence, and physical validation. |
| DR12 | Complete ML-DSA-44 `Sign`. | Complete signing, including approved pure/prehash interfaces and deterministic/hedged modes where applicable. | Mode/interface vectors, rejection-loop behavior, signature serialization, source-mode behavior, lifecycle, and physical evidence. |
| DR13 | Complete ML-DSA-44 `Verify`. | Complete verification, including approved pure/prehash interfaces where applicable. | Positive, negative, mutation, malformed-signature, and malformed-message cases with terminal-only result/status. |
| DR14 | Complete ML-DSA-65. | NPU-resident `KeyGen`, `Sign`, and `Verify` with every approved interface and applicable signing mode. | Full ML-DSA-65 ACVP/vector coverage, lifecycle, negative testing, and physical evidence. |
| DR15 | Complete ML-DSA-87 and primary closure. | NPU-resident ML-DSA-87 `KeyGen`, `Sign`, and `Verify`, followed by integrated FIPS 202/203/204 evidence review. | All FIPS 202 functions, FIPS 203 sets/operations, and FIPS 204 sets/operations accepted. This is the primary 100% NPU closure. |

### 6.1 DR8 FIPS 203 closure

DR8 generalizes the accepted ML-KEM-512 operation graphs to ML-KEM-768 and
ML-KEM-1024 without weakening any existing residency rule.

- Every approved ML-KEM parameter set and public operation is implemented.
- Parameter-dependent dimensions, eta values, compression widths, byte
  lengths, loops, FIFO capacities, and terminal records are explicit, not
  inferred from ML-KEM-512 constants.
- All applicable vendored ACVP cases pass for each parameter set and operation.
- K-PKE remains an internal component and is not presented as an approved
  standalone public encryption scheme.
- DR8 closes only when ML-KEM-512, ML-KEM-768, and ML-KEM-1024 have complete
  operation, negative/error, lifecycle, and physical evidence.

### 6.2 DR9 FIPS 202 closure

DR9 turns the proven Keccak/SHAKE building blocks into a complete reusable NPU
FIPS 202 service.

- Implement SHA3-224, SHA3-256, SHA3-384, SHA3-512, SHAKE128, and SHAKE256.
- Validate fixed and variable message lengths, padding boundaries, multi-block
  absorb, multi-block squeeze, and variable XOF output lengths.
- Keep Keccak state, absorbed material, and squeezed intermediates on the NPU.
- Permit only the requested final digest or XOF record to leave the NPU.
- Remove all host `hashlib` or equivalent cryptographic work from in-scope
  production PQC operations.

### 6.3 DR10 source and sealed-lifecycle architecture

DR10 provides three required source modes plus a sealed lifecycle:

1. **External raw ingress:** The host or an external system may supply raw
   entropy, randomness, messages, public inputs, ciphertexts, or key material
   through declared DMA ingress. Cryptographic conditioning, derivation,
   sampling, transformation, and use occur only on the NPU.
2. **NPU-native entropy:** NPU-generated entropy requires a separately
   validated physical entropy source and DRBG, startup/continuous health tests,
   reseed behavior, provenance, failure behavior, and fail-closed operation.
   A timer, unvalidated noise source, or deterministic PRNG is not sufficient.
3. **Authenticated external key material:** External key material, including
   QKD network material, enters through a defined adapter with source
   authentication, provenance binding, freshness/replay handling, purpose and
   parameter-set domain separation, and fail-closed rejection. QKD transport
   alone is not evidence of authentication or correct algorithm binding.
4. **Sealed lifecycle:** Chained operations retain private keys, seeds,
   randomness, intermediate ciphertexts, signatures, and shared secrets in
   NPU-managed internal state when the selected workflow does not require
   public egress. No host-visible intermediate is permitted between chained
   operations.

All source modes must map raw material to the exact standardized algorithm
inputs without silently changing FIPS 203 or FIPS 204 semantics. A future
FIPS 205 adapter requires a separately approved roadmap revision.

### 6.4 DR11 through DR15 FIPS 204 closure

DR11 through DR13 complete ML-DSA-44 operation by operation. DR14 generalizes
all approved operations to ML-DSA-65. DR15 generalizes them to ML-DSA-87 and
performs the integrated primary closure.

Primary closure requires:

- All three approved ML-DSA parameter sets.
- `KeyGen`, `Sign`, and `Verify` entirely on the NPU.
- Every approved pure/prehash interface and deterministic/hedged signing mode
  applicable to the accepted standard interface.
- Complete SHAKE use, ExpandA/ExpandS/ExpandMask, NTT-domain arithmetic,
  rejection loops, decomposition, hints, norm checks, codecs, signature/key
  assembly, and verification comparison on the NPU.
- Applicable ACVP and independent vector coverage, malformed-input and
  mutation tests, repeated requests, lifecycle/zeroization, resource fit, and
  physical evidence.

DR15 is the **primary 100% NPU implementation gate**. It cannot close unless
every DR through DR15 is accepted and integrated evidence demonstrates full
FIPS 202, FIPS 203, and FIPS 204 coverage under Section 1.1.

### 6.5 Future FIPS 205 and FIPS 206 work

FIPS 205 and FIPS 206 are not part of the active numbered DR sequence.

- FIPS 205 is finalized but deferred as future work.
- FIPS 206 remains under development and is also future work.
- Neither standard may begin automatically after DR15.
- Neither standard has an assigned DR number, branch, implementation plan, or
  publication authorization.
- Starting either standard requires a separate roadmap revision that defines
  parameter sets, operations, dependencies, source modes, validation corpora,
  physical evidence, and publication gates, followed by explicit user
  approval.

## 7. Universal architecture invariants

These invariants apply to all completed DRs and all approved later DRs unless an
explicit user-approved roadmap revision changes them.

1. **Two-channel maximum:** Phoenix permits at most two input DMA channels per
   core boundary.
2. **Exactly two host fills:** Every public operation graph performs exactly
   two host fills. Packing multiple fields into one request does not widen this
   boundary.
3. **Terminal-only transfer:** After dispatch, only the declared complete
   terminal record may transfer to the CPU.
4. **Private-state containment:** Private intermediates remain in internal
   ObjectFIFOs or tile-local memory. Debug, convenience, retry, and fallback
   paths may not expose them to the host.
5. **Native-only execution:** The device graph is the execution path. A missing
   runtime, build failure, load failure, dispatch fault, or malformed result
   is not permission to execute a reference implementation.
6. **Fail closed:** Every error has a fixed, specified terminal or raised-error
   contract with no partial success and no private payload.
7. **Explicit lifecycle:** Every DR identifies and validates private-state
   initialization, request reuse, normal cleanup, error cleanup, and applicable
   reset boundaries.
8. **On-device serialization:** Encoding, compression, hashing, concatenation,
   and key/ciphertext assembly belonging to an operation occur on device.
9. **Source provenance:** Every entropy or key source is bound to source
   identity, purpose, algorithm, parameter set, operation, freshness, and
   lifecycle context before use. Cross-operation or cross-parameter reuse is
   prohibited unless the standard defines it and the implementation validates
   it.
10. **NPU-native entropy gate:** NPU-native entropy cannot be claimed without a
    separately validated entropy source, DRBG, health tests, reseed policy, and
    fail-closed behavior.
11. **Authenticated QKD/external ingress:** QKD and other external key material
    require authenticated acceptance, provenance, freshness/replay protection,
    domain separation, and standardized input mapping before NPU use.
12. **Sealed lifecycle:** Supported chained workflows keep private
    inter-operation state internal and expose no host intermediate.
13. **Evidence before claims:** No performance, security, robustness,
   constant-time, side-channel, fault-resistance, or certification claim is
   permitted without evidence supporting that exact claim.
14. **Canonical runner boundary:** `run_all_silicon_tests.py` is not changed
    without separate explicit user approval.
15. **Repository hygiene:** Unrelated tracked and untracked files are not
    modified, deleted, staged, archived, or normalized.

## 8. Per-DR acceptance checklist

### 8.1 Design and ABI

- [ ] The DR number, operation, dependencies, and non-claims are accepted.
- [ ] Inputs, descriptor, byte lengths, ObjectFIFO topology, host fills, DMA
      channels, and terminal output are specified.
- [ ] The graph has exactly two host fills and no more than two input DMA
      channels per relevant core boundary.
- [ ] The terminal output is complete, fixed, and the sole post-dispatch CPU
      transfer.
- [ ] All required device cryptographic stages and serialization steps are
      enumerated.

### 8.2 Correctness and failure behavior

- [ ] Independent reference logic is confined to tests and cannot be loaded as
      a production success path.
- [ ] Applicable standard vectors, ACVP cases, deterministic inputs, expected
      outputs, and versions are traceably identified.
- [ ] All required cases pass. DR2 specifically requires all 25 applicable
      KeyGen ACVP cases.
- [ ] Terminal framing, length, byte order, status, sentinel replacement, and
      serialized bytes are verified.
- [ ] Invalid public inputs fail before native loading where possible.
- [ ] Descriptor, bounded sampler, private-token, terminal-record, runtime,
      build/load, and execution failures fail closed as applicable.
- [ ] Repeated requests in one process prove state reset.

### 8.3 Residency and lifecycle

- [ ] Source and runtime evidence show no intermediate CPU drain or
      host-mediated continuation.
- [ ] Private intermediates remain in internal FIFOs/tile memory.
- [ ] No production reference fallback exists.
- [ ] Private-state lifetime and zeroization are documented and tested for
      normal, error, reuse, and applicable reset boundaries.
- [ ] DR7 specifically demonstrates implicit-rejection behavior without a
      rejection oracle.

### 8.4 Physical evidence

- [ ] Native backend label and exact corpus pass count are recorded.
- [ ] Repeated native runs pass without stale worker state.
- [ ] Worker ELF section sizes and linker program/data/stack allocations fit.
- [ ] Logical and placed FIFO topology, depth, buffers, banks, and flows match
      the design.
- [ ] Shim DMA allocations expose only the two ingresses and terminal egress.
- [ ] xclbin, PDI, partition, memory-topology, cache/build identity, toolchain,
      and device identity are retained.
- [ ] `git diff --check`, focused host tests, static contracts, lint, and the
      ordered zero-skip host regression pass.
- [ ] No canonical runner change occurred without separate approval.

### 8.5 Governance and acceptance

- [ ] Work remained local for the entire incomplete DR.
- [ ] No incomplete DR or sub-milestone branch or pull request was pushed.
- [ ] Unrelated files remained untouched.
- [ ] The closure record is complete and requests explicit user acceptance.
- [ ] The user explicitly accepted the completed DR.
- [ ] The complete accepted DR was pushed immediately before the next DR began.
- [ ] No work on the next DR began early.

### 8.6 Final standards-coverage matrix

| Acceptance domain | DR8 | DR9 | DR10 | DR11–DR15 |
|---|---:|---:|---:|---:|
| Exact NPU operation and parameter-set boundary documented | Required | Required | Required | Required |
| No CPU cryptographic transform or intermediate drain | Required | Required | Required | Required |
| At most two input DMA channels; exactly two host fills for public graphs | Required | Required | Required | Required |
| Terminal-only output and defined fail-closed behavior | Required | Required | Required | Required |
| Standard vectors/ACVP as applicable with retained provenance | Required | Required | Required where applicable | Required |
| Complete parameter/function coverage | ML-KEM-512/768/1024 | All six FIPS 202 functions | All accepted source modes | ML-DSA-44/65/87 |
| Source provenance, domain separation, freshness, and health behavior | Integrated | Integrated | Closure requirement | Integrated |
| Sealed-lifecycle chaining evidence | Integrated | Integrated | Closure requirement | Required where chained |
| Zeroization plus negative/error-path evidence | Required | Required | Required | Required |
| Repeated silicon and build-image evidence | Required | Required | Required | Required; DR15 integrates primary closure |
| Explicit acceptance and immediate push before successor | Required | Required | Required | Required |

DR15 closes the primary program only when the integrated evidence demonstrates
complete NPU-resident FIPS 202, FIPS 203, and FIPS 204 coverage. FIPS 205 and
FIPS 206 remain outside this numbered acceptance matrix until a separate
user-approved roadmap revision assigns their future boundaries.

## 9. Required closure record

Every completed DR retains a local closure record containing:

1. DR identifier, accepted scope, date, status, reviewer, and explicit
   acceptance reference.
2. Exact ingress, descriptor, host-fill, DMA, internal-token, terminal-record,
   byte-length, and serialization contracts.
3. Local commit identifiers, patch lineage, repository-state notes, and
   confirmation that unrelated files were untouched.
4. Build, toolchain, device, worker image, xclbin/PDI, partition, and memory
   identities.
5. Vector or ACVP corpus identity, commands, pass/fail totals, retained logs,
   and expected-result provenance.
6. Evidence for terminal-only host visibility, private-intermediate residency,
   native-only behavior, fail-closed paths, repetition, and zeroization.
7. Placement, worker sections, stack, FIFO, buffer, bank, DMA, and shim
   evidence.
8. All limitations, exclusions, unresolved observations, and separately
   approved waivers.
9. The explicit user acceptance and the subsequent publication decision.

No implied waiver is permitted. An unresolved mandatory item leaves the DR
open.

## 10. Publication and branch policy

1. **Local while incomplete:** No incomplete DR milestone or sub-milestone
   branch or pull request is pushed to GitHub. Local commits and patches are
   allowed.
2. **No early remote review artifact:** Do not create or update a remote branch
   or pull request for any incomplete DR2 through DR15 milestone or
   sub-milestone.
3. **Closure gate:** A DR becomes eligible to push only after the full
   acceptance checklist and closure record are complete and the user explicitly
   accepts the DR.
4. **Immediate accepted push:** Push the complete accepted DR immediately
   before beginning the next DR.
5. **No overlap:** Never start the next DR before the current closure record,
   user acceptance, and required push are complete.
6. **Completed push state:** DR0 through DR5 are pushed and physically
   validated. The `main` branch reflects the complete accepted state of all
   closed milestones.
7. **Repository boundaries:** Do not touch unrelated files and do not modify
   `run_all_silicon_tests.py` without separate explicit approval.

## 11. Scope and non-claims

### 11.1 In scope

- Device-residency boundaries, milestone dependencies, ABIs, validation gates,
  evidence requirements, and local-first publication governance.
- DR0, DR1, DR2a, DR2b, DR2c, and DR2d as frozen/completed baselines.
- DR3, DR4, and DR5 as completed and physically validated milestones.
- DR6 and DR7 as the accepted future complete ML-KEM-512 operation sequence.
- DR8 as complete all-parameter-set FIPS 203 closure.
- DR9 as complete reusable FIPS 202 closure.
- DR10 as external, NPU-native, QKD/external-key, and sealed-lifecycle source
  architecture.
- DR11 through DR15 as complete FIPS 204 operation and parameter-set closure.
- FIPS 205 and FIPS 206 as explicitly retained, unnumbered future work.

### 11.2 Not claimed or authorized

- This document does not mark any open implementation complete or authorize a
  successor to start before its predecessor's closure gate.
- It does not claim performance, latency, throughput, power, utilization,
  constant-time behavior, side-channel resistance, fault resistance, security
  assurance, interoperability beyond recorded tests, ACVP validation status,
  FIPS validation, certification, or production readiness.
- DR6's deterministic 32-byte input is a test boundary, not an approved
  production entropy architecture.
- DR10 does not approve a production NPU entropy source merely by defining its
  interface. The entropy source, DRBG, and health tests require separate
  physical and cryptographic evidence.
- QKD transport does not by itself establish source authenticity, freshness,
  correct domain separation, or safe use by a FIPS algorithm.
- FIPS 205 and FIPS 206 have no assigned DR. Both require a separate
  user-approved roadmap revision before numbering, authorization, or
  implementation; FIPS 206 also remains contingent on its final standard.
- This document does not authorize a canonical-runner change, modification of
  unrelated files, remote publication of incomplete work, or reference
  fallback.

## 12. User review and decision record

Approval of this roadmap freezes milestone boundaries and governance. It does
not mark any implementation DR complete; each DR still requires its own
closure record and explicit acceptance.

### 12.1 Existing status and numbering

- [x] Approved: Keep DR0, DR1, DR2a, DR2b, and DR2c
      frozen as documented.
- [x] Approved: DR2d closed DR2. DR2 is COMPLETE /
      PHYSICALLY VALIDATED.
- [x] Approved: DR3 (K-PKE.Encrypt) is COMPLETE /
      PHYSICALLY VALIDATED (25/25 ACVP PASS).
- [x] Approved: DR4 (K-PKE.Decrypt) is COMPLETE /
      PHYSICALLY VALIDATED (25/25 ACVP PASS).
- [x] Approved: DR5 (ML-KEM.KeyGen) is COMPLETE /
      PHYSICALLY VALIDATED (25/25 ACVP PASS).
- [x] Approved: Reserve DR6 for `ML-KEM.Encaps`.
- [x] Approved: Reserve DR7 for `ML-KEM.Decaps` and
      end-to-end ML-KEM-512 closure.
- [x] Approved: Reserve DR8 for all-parameter-set
      FIPS 203 closure.
- [x] Approved: Reserve DR9 for complete reusable
      FIPS 202 closure.
- [x] Approved: Reserve DR10 for entropy/key-source
      modes and sealed lifecycle.
- [x] Approved: Reserve DR11 through DR15 for full
      ML-DSA-44/65/87 and primary FIPS 202/203/204 closure.
- [x] Approved: Keep finalized FIPS 205 as unnumbered
      future work requiring a separate roadmap revision.
- [x] Approved: Keep FIPS 206 as unnumbered future
      work requiring its final standard and a separate roadmap revision.

### 12.2 Completed DR closure boundaries

- [x] DR2d: 25/25 ACVP PASS. All conditions in Section 4.2 verified.
- [x] DR3: 25/25 ACVP PASS. All conditions in Section 4a.2 verified.
- [x] DR4: 25/25 ACVP PASS. All conditions in Section 4b.2 verified.
- [x] DR5: 25/25 ACVP PASS. All conditions in Section 4c.2 verified.

### 12.3 Accepted future interfaces

- [x] Approved: DR6 packed `ek + deterministic input`
      ingress and one terminal `c + K` record.
- [x] Approved: DR7 packed `dk + c` ingress, terminal
      `K`, and no rejection oracle.
- [x] Approved: DR8 covers ML-KEM-512, ML-KEM-768,
      and ML-KEM-1024 `KeyGen`, `Encaps`, and `Decaps`.
- [x] Approved: DR9 covers all six FIPS 202
      SHA-3/SHAKE functions.
- [x] Approved: DR11 through DR15 cover every approved
      ML-DSA parameter set, operation, interface, and applicable signing mode.
- [x] Approved: Do not assign interfaces or operation
      boundaries for FIPS 205 or FIPS 206 in this roadmap.

### 12.4 Source and sealed-lifecycle modes

- [x] Approved: Permit host/external raw entropy and
      key ingress while requiring all cryptographic conditioning and use on the
      NPU.
- [x] Approved: Require separately validated
      NPU-native entropy, DRBG, health tests, provenance, and fail-closed
      behavior.
- [x] Approved: Permit authenticated QKD/external key
      ingress with provenance, freshness/replay handling, purpose/algorithm/
      parameter domain separation, and NPU-resident acceptance/use.
- [x] Approved: Require sealed lifecycle mode with no
      host-visible private intermediate between chained NPU operations.

### 12.5 Invariants and governance

- [x] Approved: Keep the two-channel maximum, exactly
      two host fills, terminal-only output, internal private state, native-only,
      and fail-closed invariants.
- [x] Approved: Keep the acceptance checklist and
      closure-record requirements.
- [x] Approved: Keep the local-only-until-acceptance
      policy and immediate accepted-push rule.
- [x] Approved: Keep the prohibition on touching
      unrelated files or modifying `run_all_silicon_tests.py` without separate
      approval.
- [x] Approved: Keep the prohibition on unsupported
      performance, security, and certification claims.

### 12.6 Decision

| Field | Record |
|---|---|
| Reviewer / user | Midhat Nashar |
| Review date | 2026-08-17 (Initial), 2026-08-28 (DR2d/DR3/DR4/DR5 Silicon Closure) |
| Overall roadmap decision | **APPROVED & ACTIVE** |
| Completed & Validated | DR0, DR1, DR2a, DR2b, DR2c, DR2d, DR3, DR4, DR5 (100% Silicon Validated) |
| Next Immediate Milestone | **DR6 (ML-KEM-512 ML-KEM.Encaps)** |
| Approved sequence | DR6 through DR15 for full FIPS 202, 203, 204 on-device completion |
| Required changes | FIPS 205 and FIPS 206 retained as unnumbered future work |
| Deferred boundaries | All FIPS 205 and FIPS 206 DR numbering and operation boundaries |
| Acceptance reference | DR5 100% Silicon Pass (25/25 ACVP) on AMD Phoenix NPU (2026-08-28) |

DR0 through DR5 are **CLOSED / PHYSICALLY VALIDATED ON SILICON**.

The immediate next milestone to implement is **DR6 (ML-KEM-512 ML-KEM.Encaps)**,
followed by DR7 (`ML-KEM.Decaps`), DR8 (FIPS 203 full parameter-set closure),
DR9 (FIPS 202 service), DR10 (entropy/lifecycle), and DR11–DR15 (ML-DSA-44/65/87
and primary FIPS 202/203/204 closure).
