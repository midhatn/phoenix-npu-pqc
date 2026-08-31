# PQC DR1 Design: ML-DSA-44 ExpandA / RejNTT

**Status:** narrow physical Phoenix PASS recorded on 2026-08-17.  See
`PQC_DR1_SILICON_VALIDATION_PENDING.md` for the exact corpus, log identity,
compiler-reported sizes, incident history, and claim boundary.

## Scope

`DR1_MLDSA44_EXPANDA_REJNTT` generates **one** ML-DSA-44 matrix polynomial per
request:

$$
\hat A[i][j] = \mathrm{RejNTTPoly}(\mathrm{SHAKE128}(\rho\mathbin\Vert[j]\mathbin\Vert[i]))
$$

where `j` is the column byte and `i` is the row byte, each in `0..3`.  This is
intentionally not a generic SHAKE service, not a full matrix operation, and
not an implementation for ML-DSA-65 or ML-DSA-87.

The normative algorithm references are [NIST FIPS 202]
(https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf) for SHAKE128 and
Keccak-f[1600], and [NIST FIPS 204]
(https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf) for ML-DSA ExpandA,
`CoeffFromThreeBytes`, and the ML-DSA-44 parameters.

## Fixed ABI v1

All fields wider than one byte are little-endian.

| Item | Size | Layout |
|---|---:|---|
| `rho` | 32 B | exactly `rho[32]` |
| descriptor | 16 B | version `1`; opcode `0x11`; parameter `0x44`; flags `0`; `j`, `i`; block cap `8`; reserved byte `0`; `request_id` as u32 LE; final four reserved zero bytes |
| internal `XofBlockV1` | 180 B | request ID u32; sequence u16; `bytes_valid` u16; producer status u32; 168 data bytes |
| terminal `Dr1RejNttResultV1` | 1040 B | magic `0x44523152`; echoed request ID; status u32; accepted count u16; blocks executed u8; reserved zero; 256 signed i32 coefficient lanes |

The graph has exactly two host-ingress ObjectFIFOs (`dr1_rho` and
`dr1_descriptor`), exactly one internal ObjectFIFO (`dr1_xof_block`), and one
terminal ObjectFIFO (`dr1_result`).  Runtime performs two fills and one
terminal drain.  The result tensor is the only object transferred with
`.to("cpu")`.

## Device sequence and bounded behavior

The Keccak worker validates the descriptor before it accepts coordinates.  For
a valid request it clears its 200-byte Keccak state, absorbs the exactly
34-byte message `rho || j || i`, applies SHAKE128's `0x1f` suffix and padding,
and produces eight sequential 168-byte rate blocks.  It does not reabsorb the
message or regenerate a squeezed prefix between tokens.  The worker clears its
state, seed, and descriptor storage after its eighth token.  A malformed
descriptor still produces eight zero-data tokens with producer status
`DR1_BAD_DESCRIPTOR`; this preserves the fixed schedule and prevents an
unconsumed-token deadlock.

The sampler drains all eight tokens.  It forms each candidate as
`z = (b0 | b1<<8 | b2<<16) & 0x7fffff`, accepts only `z < 8380417`, and freezes
the first 256 accepted values while continuing to drain the remaining tokens.
It preserves a two-byte tail state even though the fixed SHAKE128 rate is
currently divisible by three.  The terminal result is written only after the
eighth block.

| Status | Accepted count | Blocks | Coefficient lanes |
|---|---:|---:|---|
| `0 DR1_OK` | 256 | 8 | 256 canonical values in `[0, 8380417)` |
| `1 DR1_LIMIT_EXCEEDED` | 0 | 8 | all zero |
| `2 DR1_BAD_DESCRIPTOR` | 0 | 8 | all zero |

Eight blocks are a bounded liveness specialization, not a statement that this
limit or its failure policy is sufficient for any broader standard-conformance
claim.  A host preinitializes the terminal buffer with invalid magic and
`INT32_MIN` coefficient lanes, then validates the entire returned header,
request echo, status, count, block count, reserved byte, and canonical/zero
payload contract.  It never invokes a Python or reference fallback.

## Implementation boundaries

Production files are local to `phoenix_sdr_dsp/pqc`; the C++ Keccak code is
also production-local and does not include code from `tests/`.  The test-only
oracle uses `hashlib.shake_128` independently.  A test-only four-block oracle
specialization proves that 224 candidates cannot produce a partial success and
must report a bounded failure; it does not widen the public production ABI.

## Program-size and IRON linkage gate

Phoenix AIE2 has a documented 16 KiB program-memory constraint in the project
architecture record.  The 24-round `keccak_f1600`, the SHAKE block dispatcher,
and the sampler dispatchers are explicitly `__attribute__((noinline))`; the
Clang/AIE builds also receive disabled-loop-unroll pragmas around the relevant
counted loops.  Those are source-level safeguards against cloning a complete
state machine across the eight scheduled calls, not measured fit
evidence.  A **compiler-reported program size** for each placed worker is a
mandatory physical acceptance artifact.

The original v1 DR1 shape declared eight producer and eight sampler
`ExternalFunction` objects that repeated a `source_file`.  A physical IRON
1.4.1 build compiled each declaration into a separate object, each object
exported all eight C wrappers, and `ld.lld` rejected duplicate
`dr1_shake128_emit_block_0..7` and `dr1_rejntt_consume_block_0..7` symbols.
No device program executed.  The redesign exposes one C entry point per
source—`dr1_shake128_emit_next` and `dr1_rejntt_consume_next`—and declares each
`ExternalFunction` once.  Each worker calls its one entry point eight times
with state retained in its core-local `g_service` or `g_sampler`.

The v2 single-entrypoint redesign subsequently compiled, linked, routed, and
executed on Phoenix and returned a syntactically valid SUCCESS terminal record,
but its coefficient 0 disagreed with the independent SHAKE128 oracle.  Its 256
values were unique, not a repeated first-block pattern.  The host-correct
table-based Keccak is therefore suspected, but not proven, to be incompatible
with Peano/AIE2 code generation or read-only-data handling.

V3 keeps the topology and one-entrypoint design, but replaces the permutation
with a source-local structural match to the physically proven M32c approach:
an explicitly aligned `uint8_t[200]` state viewed as lanes, on-the-fly FIPS 202
LFSR Iota constants, and the Rho/Pi orbit recurrence.  V3 physically compiled,
linked, placed, routed, and executed on Phoenix through IRON 1.4.1.  Its frozen
33-case corpus passed all 8,448 exact coefficient comparisons.  Peano reported
6,608 bytes of `.text` for the SHAKE worker on core `(0,2)` and 3,328 bytes for
the RejNTT worker on core `(0,3)`, both below the 16 KiB program-memory gate.

The normal graph contract always makes eight calls.  As a defensive host-harness
case, a changed rho/descriptor or request ID resets an interrupted local
producer/sampler sequence before the next request.  An interrupted retry with
the *same* rho, descriptor, and request ID has no separate sequence-start field
in the fixed ABI and is therefore not an independently recoverable case; it
relies on the fixed eight-call worker schedule.

## Non-claims

The physical PASS is limited to one ML-DSA-44 `ExpandA` / `RejNTT` polynomial
per request under this fixed ABI and successful-request corpus.  This
implementation makes **no** claim of complete FIPS 204 device residency, full
FIPS 204 conformance, performance or throughput improvement, constant-time behavior are not claimed
behavior, secure zeroization, side-channel resistance, CMVP validation, or
CMVP certification.  Malformed-descriptor and internal-token corruption paths
were not exercised physically in this corpus.
