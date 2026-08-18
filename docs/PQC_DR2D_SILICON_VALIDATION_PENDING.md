# DR2d Silicon Validation Record

**Status: NO PASSING INTEGRATED PHYSICAL RESULT.** No passing integrated DR2d
production result or complete production-acceptance bundle is recorded here.
Historical physical failure and diagnostic observations are documented below;
they do not establish a pass or authorize a new native run.

## Host-validated implementation awaiting physical evidence

DR2d uses five independently compiled computation workers (W0–W4) plus
serializer W5, rather than the prior monolithic derive program:

1. seed/G derivation plus all secret/error CBD3/NTT noise;
2. row-0 matrix expansion;
3. row-0 accumulation and carried state;
4. row-1 matrix expansion;
5. row-1 accumulation/final private token;
6. terminal serialization.

It retains exactly two public ingress fills (`d[32]` and descriptor[16]), five
internal-only fixed-layout private FIFO records (2,096; 3,120; 2,096; 3,120;
2,112 bytes), one 1,588-byte terminal drain, and one result CPU transfer. The
private FIFOs have no shim route. Input descriptor/status/request validation,
canonical lane validation at every consuming boundary, fixed-zero errors, and
success/reachable-error zeroization are host-tested.

The focused host gate includes all 25 pinned NIST ACVP-Server FIPS 203
ML-KEM-512 KeyGen cases and links every production partition kernel. That is
not physical proof. The current `run_all_silicon_tests.py` is native-only, but
it deliberately never dispatches this DR2d gate; DR2d remains unresolved.

## Diagnostic physical follow-up

The first six-core physical build (five computation workers plus serializer)
compiled, fit, and executed. Its `rho`
suffix matched expected output exactly, while both `dkPKE` and `t_hat` rows
diverged from byte zero. The first working hypothesis was target-side noise
CBD3/NTT representation.

The active W0 follow-up replaces the packed-uint16 in-place NTT with the
physically validated DR2b formulation: direct-bit CBD3 into local
`uint32_t coefficients[256]`, noinline uint32 NTT using the same frozen zeta
table, then uint16 token serialization. It is host-checked against the
independent DR2b reference for all four counters in every pinned KeyGen case.
This repair was freshly rebuilt in cache directory
`04f147d54cb01d160974a6e6` at 01:18: its cached W0 source timestamp was
01:17:25, its object was created at 01:18:09, and the build produced six fresh
ELFs and `final.xclbin`. Case 1 nevertheless remained byte-for-byte identical
to the pre-repair failure: `rho` remained exact, `ekPKE` SHA-256 remained
`6e6a50c8...05dc3`, and `dkPKE` SHA-256 remained
`a2055b7f...2e42d37`, with both key components differing from byte zero.
Stale source/cache is therefore ruled out, and this result does **not**
localize the fault to W0; it keeps private-token preservation/handoff,
final-token contents, serializer behavior, and target-specific arithmetic in
scope.

MLIR inspection subsequently proved the six expected symbols, FIFO sizes, and
depth-two allocation. Its address allocation places the secret token at
`tile0_2` banks 0/1; row-0 matrix at `tile0_3`; row state at `tile0_4`;
row-1 matrix producer at `tile0_5` and consumer at `tile1_2` banks 0/1; final
token at `tile1_2` banks 2/3; and result at `tile1_3`. Simultaneous
input/output ranges are distinct. The temporary overlap-guard experiment is
therefore not part of DR2d.

The next artifact is a separate, diagnostic-only two-worker terminal probe. It
accepts the same two public fills, recognizes only case-1's fixed request ID,
writes deterministic canonical `t_hat[0..1]`, `s_hat[0..1]`, and `rho` into
one private final-token FIFO, then calls the unchanged production serializer.
It has one normal 1,588-byte terminal record and no additional host fill,
drain, CPU transfer, shim route, fallback, or canonical-runner entry.

The terminal probe returned an ABI-valid case-1 record with correct header
fields and exact `rho`, but a CRC32 over a wrong payload. All four polynomials
showed the same defect: odd lanes were correct while the high four bits of each
even lane were cleared. For example, expected `ff2ccf...` became `ff20cf...`,
converting even coefficient `0x0cff` to `0x00ff`; the first t0 and s0 failures
occurred exactly at even lanes 20 and 24 once their values exceeded 255.

Fresh cache `65327e...` confirmed the widened serializer source/object at
01:48, and a subsequent raw-byte serializer rebuild also left output
byte-for-byte unchanged. Dispositive ELF inspection of the failing diagnostic
producer `core_0_2` found each coefficient loop's high-byte `st.s8` directly
in its ZOL loop-end bundle: low/high stores at `0x8ac/0x8c0` (`.L_LEnd5`),
`0x94a/0x960` (`.L_LEnd4`), `0x9e0/0xa00` (`.L_LEnd3`), and
`0xa70/0xa90` (`.L_LEnd2`). The installed Peano is llvm-aie 21.0.0 commit
`c9c5ecb7`, ancestral to upstream fix `f1baf5a` from PR #1221. Published
Windows nightlies stop at vulnerable `2026080301`; fixed `>=2026080601`
assets are Linux-only.

This localizes the immediate diagnostic failure to byte stores in producer
coefficient loops, not serializer or FIFO. DR2b/DR2c and all relevant DR2d
workers use the same helper, so production is unchanged pending direct
evidence. The next diagnostic-only producer revision uses one alignment-checked
placement construction of one `uint32_t` per coefficient pair,
`(a & 0xffff) | ((b & 0xffff) << 16)`. This begins the destination object
lifetime without a typed-pointer assignment to `uint8_t` storage, eliminating
byte/halfword stores from those four construction loops without changing its
graph or serializer. Physical ELF inspection remains required to verify the
target emits full-word stores.

### Diagnostic full-word producer: physical PASS (2026-08-18)

The diagnostic-only full-word terminal probe **physically PASSED on Phoenix**:
it produced the exact 1,588-byte normal terminal record with SHA-256
`309c9dd65e843edb15bc67766aff8f37b302ef815a435813881d6908d567adb4` and exit
code 0. That single result physically establishes, on the vulnerable installed
toolchain, all of the following:

- an alignment-checked placement-constructed `uint32_t` per coefficient pair is
  lowered to a full-word store that survives the ZOL loop-end hazard;
- the private final-token FIFO preserves a 2,112-byte record end to end;
- the unchanged production serializer, its `encode_poly12` byte packing, its
  CRC32, and its commit-magic-last ordering are correct on target;
- `write_header`, `store_le32`, `clear_bytes`, and the 32-byte `rho` byte-store
  loop are correct on target, because the probe exercises all of them and the
  record is byte-exact.

It does **not** establish production DR2d KeyGen correctness: the probe never
runs `derive_g`, `cbd3`, `ntt`, `sample_matrix_store`, `add_product_ntt`, the
six-core topology (five computation workers plus serializer), or any of the
five private FIFO handoffs.

### Production repair now in tree (still awaiting physical evidence)

Because the defect class is confirmed and the workaround is physically proven,
every **normal-path coefficient store** in the production partition has been
converted to a full 32-bit store. The audited paths and their repairs are:

Scope is limited to **coefficient-bearing and polynomial-carry token regions**.

| Worker | Repaired destination | Offset / span | Previous store | Repaired store |
| --- | --- | --- | --- | --- |
| W0 seed/noise | secret s0/s1/e0/e1 | 48 / 560 / 1072 / 1584, 512 B each | 256 x `store_le16` | 128 x `store_pair_word` |
| W1 row-0 expand | matrix secret/s1/carry0/carry1 | 48, 8*kN = 2,048 B | byte loop | `copy_words`, 512 words |
| W1 row-0 expand | matrix A[0,0] / A[0,1] | 2096 / 2608, 512 B each | up to 256 x `store_le16` | 128 x `store_pair_word` via a buffered even lane |
| W2 row-0 accumulate | state secret/s1 | 48, 4*kN = 1,024 B | byte loop | `copy_words`, 256 words |
| W2 row-0 accumulate | state t0 seed, state e1 | 1072 / 1584, 512 B each | byte loops | `copy_words`, 128 words each |
| W2 row-0 accumulate | `add_product_ntt` into state t0 | 1072, 512 B | 256 x `store_le16` | 64 groups x 2 `store_pair_word` |
| W3 row-1 expand | matrix secret/s1/carry0/carry1 | 48, 8*kN = 2,048 B | byte loop | `copy_words`, 512 words |
| W3 row-1 expand | matrix A[1,0] / A[1,1] | 2096 / 2608, 512 B each | up to 256 x `store_le16` | 128 x `store_pair_word` via a buffered even lane |
| W4 row-1 accumulate | final s0/s1 | 64, 4*kN = 1,024 B | byte loop | `copy_words`, 256 words |
| W4 row-1 accumulate | final t0, final t1 seed | 1088 / 1600, 512 B each | byte loops | `copy_words`, 128 words each |
| W4 row-1 accumulate | `add_product_ntt` into final t1 | 1600, 512 B | 256 x `store_le16` | 64 groups x 2 `store_pair_word` |

`store_le16` no longer exists in `dr2d_mlkem512_kpke_keygen_internal.hpp`, so
no DR2d coefficient loop can regress to a 16-bit coefficient store. Every word
is produced by `::new (void *) uint32_t(word)` placement construction, which
begins a `uint32_t` object's lifetime in the token's `unsigned char` storage
rather than assigning through a cast pointer; only the permitted direction of
aliasing (byte reads of that object's representation by `load_le16`,
`load_le32`, `canonical_poly`, the serializer, and volatile `clear_bytes`) is
relied upon. Alignment is justified statically by `static_assert` on every
polynomial offset and copy span used, and dynamically by a `word_aligned` check
on each token base; a misaligned base fails closed with `BAD_TOKEN` and an
all-zero record instead of storing.

### Byte stores deliberately retained (not defects, not in scope)

The repaired workers still contain byte stores by design. Widening them is not
required to remove partial-word **coefficient** stores, and the diagnostic
probe physically validated several of these shapes. A Phoenix gate must expect
them:

| Retained byte store | Location | Destination class |
| --- | --- | --- |
| Keccak absorption, domain padding, `rho`/`sigma` extraction | `internal.hpp` `derive_g`, `sample_matrix_store` | local `alignas(8) uint8_t state[200]`, local `rho`/`sigma` |
| SHAKE256 absorption/padding and PRF buffer fill | `seed.cc` `cbd3_ntt_store_dr2b` | local `state[200]`, local `prf[192]` |
| 32-byte `rho` token copies | `seed.cc`, both expand workers, both accumulate workers | token `rho` region (not coefficient storage) |
| Header id/status fields | `write_header` / `store_le32` | token header bytes 0..7 |
| Zeroization | `clear_bytes` | volatile byte writes over any buffer |
| `ByteEncode12` packing, CRC, magic | unchanged serializer TU | terminal result record |

`rho` byte copies were explicitly **reverted** from an earlier full-word variant
so the production repair stays minimal: the physically passing probe already
exercised a 32-byte `rho` byte-store loop and produced a byte-exact record.

Deliberately **not** changed: the serializer translation unit, the terminal
probe, DR2b, DR2c, both graphs, and the ABI. All ABIs, token layouts, the two
host fills, the single terminal drain, the result-only CPU transfer, and
`run_all_silicon_tests.py` are byte-identical.

### Residual gate

The repair is host-proven only. The residual gate before any production
physical claim is:

1. **Phoenix ELF inspection of all five repaired production workers** (see the
   destination-classified requirements at the end of this document). Source
   shape cannot establish target code generation; only disassembly can. The
   inspection classifies each store by loop and destination and rejects
   sub-word stores only for coefficient/carry destinations.
2. The native 25/25 production gate on the pinned Windows IRON/XRT/Phoenix
   environment.
3. Nothing here upgrades the status. **Status remains PENDING PHYSICAL
   VALIDATION.**

**Physical discrimination plan:**

1. Fresh-build and run the diagnostic case-1 gate. A byte-exact normal
   terminal record (SHA-256
   `309c9dd65e843edb15bc67766aff8f37b302ef815a435813881d6908d567adb4`)
   proves this diagnostic artifact's pairwise full-word coefficient stores,
   final-token FIFO, and existing serializer path on Phoenix. It is a direct
   test of the fixed toolchain-lowering hazard, not a production KeyGen pass.
2. A malformed, error, or byte-mismatching terminal record keeps final-token
   preservation or target serializer lowering in scope. Capture the diagnostic
   FIFO placement, addresses, depth, program memory, and result bytes before
   changing production code.
3. This is a discriminator, not a DR2d KeyGen pass. It does not validate the
   production six-core final FIFO placement unless physical reports show the
   comparable route/allocation, and it never replaces the required native
   25/25 production gate.

## Required physical evidence before changing status

First run the diagnostic-only case-1 discriminator on the same pinned native
environment; it is intentionally outside the canonical runner:

```powershell
py .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_terminal_probe_silicon.py
```

Run the native-only command on the pinned native Windows IRON/XRT/Phoenix
environment:

```powershell
py .\tests\pqc_device_resident\test_dr2d_mlkem512_kpke_keygen_silicon.py
```

Record all of the following:

1. backend string `dr2d-mlkem512-kpke-keygen:silicon`;
2. `TOTAL 25/25 PASS`, exit code 0, and a repeat invocation in the same
   process;
3. generated artifact identities and timestamps (`final.xclbin`, PDI, cache
   key/path);
4. independently compiled worker program-memory reports for all six kernels;
5. per-tile data-memory reports including the declared stack, actual FIFO
   depth, placement, and adjacent FIFO allocation; in particular verify the
   3,120-byte matrix records can coexist with their adjacent state records,
   and W0's local 1,024-byte coefficient array plus 392-byte state/PRF
   scratch fits with the declared stack;
6. confirmation of exactly two shim MM2S channels and one terminal S2MM
   channel, with no shim route/allocation for any `dr2d_*token` FIFO;
7. explicit distinction between output correctness evidence and unvalidated
   remanence, side-channel, constant-time, performance, CMVP, or certification
   claims.

A missing runtime must print `unavailable` and exit 2; it is not a pass.

## Required Phoenix ELF inspection before production execution

The full-word repair is a code-generation workaround, so it must be verified in
the generated target code, not in source, **before** the production 25/25 run
is treated as meaningful.

### The gate is destination- and loop-classified, never a global byte-store grep

A global "no `st.s8`/`st.s16`" check is **wrong and must not be used**. The five
repaired workers legitimately contain byte stores for local Keccak/SHAKE state,
domain padding, PRF buffers, `rho`/`sigma`, token `rho` regions, header fields,
and volatile zeroization (see the retained-byte-store table above). Such a grep
would either fail a correct ELF or push a reviewer to waive a real defect.

Every store instruction found in, or adjacent to, a repaired loop must instead
be **classified by its destination** into exactly one of:

- **Class C - coefficient/carry FIFO destination.** A write into any polynomial
  region of a private token: secret 48/560/1072/1584; state 48/560/1072/1584;
  matrix 48/560/1072/1584/2096/2608; final 64/576/1088/1600. **Only full 32-bit
  stores are accepted here.** Any `st.s8`/`st.s16` in Class C is a hard failure.
- **Class L - local byte-oriented cryptographic state.** Keccak/SHAKE
  `state[200]`, domain padding, `prf[192]`, local `rho`/`sigma`. Byte stores are
  **expected and accepted**.
- **Class R - token `rho` region.** Secret/state/matrix offset 16..47 and final
  offset 32..63. Byte stores are **expected and accepted** (physically validated
  shape, deliberately not widened).
- **Class H - token/result header fields.** Bytes 0..7 of a token and the result
  header via `store_le32`/`store_le16`. Byte stores are **accepted**.
- **Class Z - volatile zeroization** from `clear_bytes`. Byte stores are
  **accepted**, and their presence is required (see gate step 6).
- **Class S - serializer output packing** in the unchanged sixth core. Byte
  stores are **accepted**; that core is already physically validated.

An unclassifiable store, or any store whose destination cannot be proved, is a
hard failure - not a waiver.

### Gate steps

1. **Provenance.** Fresh-build the production six-core artifact with the build
   cache for this artifact deleted or bypassed. Record toolchain
   versions/commits, compile/link command lines, cache key/path, per-source
   timestamps and SHA-256, per-object timestamps and SHA-256, all six core ELF
   timestamps and SHA-256, and the `final.xclbin` timestamp and SHA-256, so no
   stale object can be mistaken for the repair. Confirm exactly six worker cores:
   five computation workers plus serializer, and their ELF mapping.
2. **Disassemble the five repaired cores** with symbol and source correlation:
   seed/noise, row-0 expand, row-0 accumulate, row-1 expand, row-1 accumulate.
   The serializer core is unchanged and already physically validated.
3. **Build the repaired-loop map.** For each loop record entry, `.L_LEnd*`
   bundle, destination region, destination class, instruction width, and trip
   count or equivalent vectorized lane coverage:
   - W0: four `cbd3_ntt_store_dr2b` coefficient outputs, 128 pair commits each.
     The 32-byte `rho` copy is Class R and the SHAKE/PRF loops are Class L.
   - W1: the 512-word `copy_words` at matrix offset 48 covering 2,048 bytes, and
     SampleNTT A[0,0] and A[0,1] at 2096/2608 with 128 pair commits each. The
     32-byte `rho` copy is Class R.
   - W2: `copy_words` of 256 words at state offset 48, 128 words at 1072, 128
     words at 1584, then two `add_product_ntt` calls of 64 groups x 2 pair-word
     commits into state 1072. The 32-byte `rho` copy is Class R.
   - W3: same shape as W1 with A[1,0] and A[1,1].
   - W4: `copy_words` of 256 words at final offset 64, 128 words at 1088, 128
     words at 1600, then two `add_product_ntt` calls of 64 groups x 2 pair-word
     commits into final 1600. The 32-byte `rho` copy is Class R.
4. **Class C acceptance.** For every Class C write: require `st.s32` or a
   documented equivalent full-32-bit/vector store with demonstrably complete
   lane coverage; require no `st.s8`/`st.s16`, especially in every `.L_LEnd*`
   bundle; check both halves of each pair word and every loop tail, allowing no
   scalar partial-width remainder. Compare bundle placement with the pre-repair
   failing addresses `0x8ac/0x8c0`, `0x94a/0x960`, `0x9e0/0xa00`, `0xa70/0xa90`;
   addresses may move, but those repaired loop ends must contain only accepted
   full-word Class C writes.
5. **Classify the remainder.** Map every remaining `st.s8`/`st.s16` in or
   adjacent to a repaired loop to its source line and destination class. Accept
   only proved Class L, R, H, Z, or S destinations. Do not use a global
   "no byte stores" grep as the gate.
6. **Guards and fail-closed lowering.** Prove the token-base `word_aligned` test
   dominates every placement-constructed Class C store; that misalignment
   branches reach the full-record clear/`BAD_TOKEN` path and cannot fall through
   to a word store; that SampleNTT exhaustion reaches `LIMIT_EXCEEDED`; and that
   the five input-token clear loops, W0 ingress/local clears, and the serializer
   final-token clear are present and not optimized away.
7. **Layout and arithmetic lowering.** Confirm `store_pair_word` preserves
   low-lane/upper-lane order on little-endian AIE, and record evidence that the
   `__BYTE_ORDER__` assertion was active in the compile log or separately prove
   the target is little-endian. Confirm no transform changes SampleNTT candidate
   order or drops the buffered `pending` lane across XOF block transitions, and
   that each accumulation group loads all four old accumulator lanes before its
   two stores.
8. **Memory reports.** Record per-worker program-memory and per-tile
   data-memory/stack reports. The repair adds only a buffered lane in
   `sample_matrix_store` and a four-lane reduction array in `add_product_ntt`;
   every worker must still fit its declared stack with no overflow or unintended
   spill route. Confirm five private FIFOs, no private-token shim/host route,
   two fills, one terminal drain, and result-only CPU transfer.
9. **Unchanged sixth core.** Verify the serializer source hash is unchanged and
   record its ELF provenance. No acceptance may depend on rebuilding it from
   different source.
10. **Only after 1-9 pass**, run the native production gate through the
    byte-identical canonical runner. A production physical pass requires
    `TOTAL 25/25 PASS`, exit code 0, and a repeat invocation in the same
    process. An unavailable runtime, stale artifact, missing report, or
    unclassifiable store is a hard failure, not a waiver.

If a Class C partial-width store remains in a vulnerable ZOL bundle, stop: the
workaround did not take effect for that loop, and the correct next step is
toolchain replacement with a Peano build at or after upstream fix `f1baf5a`
(PR #1221), not further source churn.
