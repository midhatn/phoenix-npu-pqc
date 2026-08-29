# PQC DR2a Design: ML-KEM-512 Bounded SHAKE128 / SampleNTT

**Status:** narrow physical Phoenix validation complete.  On 2026-08-17 the
two-worker graph compiled, linked, placed, routed, and returned 13/13 exact
terminal polynomials on a Phoenix NPU through IRON 1.4.1.  DR2a remains a
deliberately narrow pre-KeyGen building block for the DR2 ML-KEM-512 K-PKE
KeyGen graph, not a claim that DR2 KeyGen itself is complete.

## Scope

`DR2A_MLKEM512_SAMPLENTT` returns one ML-KEM-512 matrix polynomial:

$$
\hat A[i][j] = \mathrm{SampleNTT}(
  \mathrm{SHAKE128}(\rho\mathbin\Vert j\mathbin\Vert i)).
$$

`j` is the column byte and `i` is the row byte.  Both are restricted to
`0..1`, the ML-KEM-512 dimension $k=2$.  The exact byte ordering, candidate
decoder, and acceptance predicate follow [NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf);
the SHAKE128 rate and sponge construction follow [NIST FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf).

This is not a generic SHAKE service, not a matrix/vector operation, and not
K-PKE KeyGen.  It does not yet combine a sampled matrix polynomial with the
existing NTT, CBD, accumulator, or codec workers.  This is not K-PKE KeyGen.

## Why this is the next narrow milestone

The architecture plan calls for DR1's incremental Keccak/sampling topology to
be reused by both schemes before a full operation-level graph is attempted.
The existing M32c ML-KEM `SampleNTT` wrapper generates only a finite 840-byte
stream and silently zero-fills a partial polynomial.  That behavior cannot be
the contract for a resident sampler.  DR2a replaces only that unsafe boundary
with a fixed, complete-or-error terminal ABI while retaining DR1's already
Phoenix-proven two-worker streaming topology.

Five SHAKE128 rate blocks are emitted and consumed per request:

$$
5 \times 168 = 840\ {\rm bytes} = 280\ {\rm three\mbox{-}byte\
candidate\ iterations}.
$$

This is the minimum bounded iteration limit described in FIPS 203 Appendix B.
The sampler parses each three-byte group as

$$
d_1=b_0+256(b_1\bmod16), \qquad d_2=\lfloor b_1/16\rfloor+16b_2,
$$

accepting each value only when it is less than$q=3329$.  It freezes the
first 256 accepted coefficients but still drains the remaining scheduled
tokens.  If fewer than 256 coefficients are accepted after all 280 iterations,
it clears local state and produces a fixed zero-payload `LIMIT_EXCEEDED`
terminal result; it never pads the polynomial with zero coefficients.

## Fixed ABI v1

All multi-byte fields are little-endian.

| Item | Size | Layout |
|---|---:|---|
| `rho` | 32 B | exactly `rho[32]` |
| descriptor | 16 B | version `1`; opcode `0x21`; parameter `0x52`; flags `0`; `j`, `i`; block cap `5`; reserved `0`; request ID as u32; four reserved zero bytes |
| internal `XofBlockV1` | 180 B | request ID u32; sequence u16; `bytes_valid` u16; producer status u32; 168 SHAKE bytes |
| terminal result | 528 B | magic `0x4452324D`; echoed request ID; status u32; accepted count u16; blocks executed u8; reserved `0`; 256 signed i16 coefficient lanes |

There are exactly two host ingress ObjectFIFOs (`dr2a_rho`,
`dr2a_descriptor`), exactly one internal ObjectFIFO (`dr2a_xof_block`), and
one terminal ObjectFIFO (`dr2a_result`).  The runtime performs two fills and
one terminal drain.  The result tensor is the only terminal-only tensor moved
to the host.

## Device behavior and fail-closed result

The SHAKE worker validates every descriptor before absorbing the 34-byte
message `rho || j || i`.  It applies SHAKE128's `0x1f` suffix and padding once,
then emits five sequential rate blocks without reabsorbing or regenerating a
prefix.  Bad descriptors still generate five zero-data error tokens so the
consumer drains a fixed schedule.

The sampler validates token sequence, request echo, producer status, and exact
block length.  It exposes no partial coefficient count.  Its terminal states
are:

| Status | Accepted count | Blocks | Lanes |
|---|---:|---:|---|
| `0 OK` | 256 | 5 | 256 canonical coefficients in `[0,3329)` |
| `1 LIMIT_EXCEEDED` | 0 | 5 | all zero |
| `2 BAD_DESCRIPTOR` | 0 | 5 | all zero |

The host preinitializes the terminal buffer with invalid magic and `0xff`
payload bytes, then validates magic, echoed request ID, status, count, block
count, reserved byte, and every lane.  A missing runtime, dispatch fault,
malformed result, bounded failure, or internal-token error never invokes a
Python/reference calculation.

## Production and test boundaries

Production code is confined to `phoenix_sdr_dsp/pqc/` and has no import or
include dependency on `tests/`.  The producer reuses DR1's source-local,
physically proven Keccak-f[1600] structural implementation, including its
aligned 200-byte state, FIPS LFSR Iota constants, and Rho/Pi recurrence.  It
does not reuse M32c's fixed wrapper.

The independent oracle in `tests/pqc_device_resident/dr2a_reference.py` uses
`hashlib.shake_128` and its own FIPS 203 parser.  The compiled harness builds
the two production C++ worker sources with `g++`, drives all five producer and
consumer calls, compares all 840 SHAKE bytes and all 256 result lanes to that
oracle, and injects malformed tokens plus a fully rejected stream.

## Program-size and topology gate

Both workers retain one C entry point and are called five times from the worker
loop.  This preserves the DR1 repair for IRON 1.4.1 duplicate-symbol behavior:
there is one `ExternalFunction` declaration per worker source, rather than one
per scheduled block.  The `noinline` Keccak and dispatcher boundaries plus
disabled loop unrolling are source-level controls only.  The physical record
in `PQC_DR2A_SILICON_VALIDATION_PENDING.md` captures compiler-reported program
size, the 16 KiB stack reservations, FIFO placement/depth/bank, DMA routes,
generated artifact identity, and repeated native execution.

## Non-claims

DR2a does not claim complete ML-KEM-512 K-PKE KeyGen, ML-KEM KeyGen/Encaps/
Decaps, complete FIPS 203 conformance, constant-time behavior, secure
zeroization, side-channel resistance, performance improvement, CMVP
validation, or CMVP certification.  The narrow physical result is recorded
separately and does not by itself add DR2a to the canonical silicon runner.
