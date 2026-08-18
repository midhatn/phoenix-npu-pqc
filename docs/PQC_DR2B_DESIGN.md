# PQC DR2b Design: ML-KEM-512 eta1 Noise-to-NTT

**Status:** physically validated on Phoenix for the narrow DR2b corpus. DR2b is a
narrow, terminal-only subgraph toward FIPS 203 K-PKE.KeyGen; it is not K-PKE KeyGen and must not be described as a complete ML-KEM operation.

## Scope and composability

For ML-KEM-512, FIPS 203 Table 2 fixes $k=2$ and $\eta_1=3$.  K-PKE.KeyGen
uses counters 0, 1 for the secret vector and 2, 3 for the error vector.  One
DR2b request computes exactly one of these four components:

$$
 \hat f = \mathrm{NTT}(\mathrm{SamplePolyCBD}_3(
 \mathrm{SHAKE256}(\sigma\mathbin\Vert b, 1536\ \mathrm{bits}))).
$$

Here `sigma` is exactly 32 bytes and the public counter `b` is strictly in
`0..3`.  SHAKE256 uses the FIPS 202 rate of 136 bytes and emits exactly the
192 bytes required by FIPS 203 PRF_3.  CBD consumes every one of those bytes in
LSB-first order, and the seven-stage FIPS 203 Algorithm 9 NTT returns 256
canonical residues in $[0,3329)$.  No SHAKE bytes or CBD-domain coefficient
returns to the host.

This is the safer next boundary than a host-orchestrated primitive wrapper:
it closes the secret-bearing sampling-to-transform path in one fixed resident
graph, leaves a single reusable NTT-domain polynomial for later KeyGen
accumulation, and does not expose a generic SHAKE/CBD service.

## Fixed ABI v1

All multi-byte fields are little-endian.

| Item | Size | Layout |
|---|---:|---|
| `sigma` | 32 B | exact K-PKE noise seed |
| descriptor | 16 B | version `1`; opcode `0x22`; parameter `0x52`; flags `0`; counter `0..3`; eta `3`; PRF bytes `192`; reserved `0`; u32 request ID; four zero reserved bytes |
| internal PRF token | 208 B | request ID u32; sequence u16=`0`; valid bytes u16=`192`; producer status u32; reserved 4 B; 192 SHAKE256 bytes |
| terminal result | 528 B | magic `0x4232524d`; echoed request ID; status u32; coefficient count u16; stage count `7`; reserved zero; 256 canonical i16 NTT lanes |

The graph has exactly two host ingress ObjectFIFOs (`dr2b_sigma`,
`dr2b_descriptor`), exactly one internal ObjectFIFO (`dr2b_prf_token`), and
one terminal ObjectFIFO (`dr2b_result`).  Runtime makes two fills and one
drain.  `result_t.to("cpu")` is the only host transfer after dispatch.

## Device schedule and failure behavior

Two workers execute a fixed single-token schedule.  The producer validates the
entire descriptor before absorbing `sigma || counter`; an invalid descriptor
emits a zero-data error token.  The consumer checks request metadata, sequence,
status, and exact length before CBD or NTT.  It writes precisely one result.

| Status | Count | Stage count | Payload |
|---|---:|---:|---|
| `0 OK` | 256 | 7 | canonical 256-lane NTT polynomial |
| `2 BAD_DESCRIPTOR` | 0 | 7 | all zero |
| `3 BAD_TOKEN` | 0 | 7 | all zero |

The host initializes the output with invalid magic and an `0xff` payload, then
validates the echoed request ID, status, count, stage count, reserved byte, and
every lane.  Invalid public inputs are rejected before IRON/XRT loading.  A
native error, malformed terminal record, or fixed device error does not invoke
host SHAKE, CBD, NTT, a reference oracle, or any fallback.

The worker implementation is request-stateless: its 200-byte Keccak state and
its CBD/NTT scratch are stack-local and explicitly cleared before return.  This
makes every scheduled call independent and prevents state carry-over across
repeated requests under the fixed ABI.

## Verification boundaries

`tests/pqc_device_resident/dr2b_reference.py` is a standards/direct independent
oracle: it uses `hashlib.shake_256`, standalone LSB-first CBD_3, and direct
modular FIPS 203 Algorithm 9 butterflies with `17^brv7(k)` twiddles.  It imports
no production DR2b module.  The required tests do not depend on kyber-py; if a
future test uses kyber-py it is only an optional, additional test-only oracle.

The compiled host harness builds both production C++ sources with strict C++17
flags and compares all 192 internal PRF bytes plus all 256 terminal NTT lanes
against that independent oracle.  It also checks repeated calls, malformed
descriptors, malformed tokens, fixed-zero error payloads, static residency,
and the native-only gate.  Host compilation is not physical proof.

## Non-claims

DR2b makes no claim of K-PKE.KeyGen, ML-KEM KeyGen/Encaps/Decaps, full FIPS 203
conformance, performance, constant-time behavior,
zeroization strength, side-channel resistance, CMVP validation, or
certification. The historical runner statement is superseded: DR2b is now the
fourth native-only canonical gate, while its narrow result still does not close
integrated DR2.

## References

- NIST FIPS 203, Algorithms 8, 9, and 13; §4.1; Table 2. https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf
- NIST FIPS 202, SHAKE256 and Keccak-f[1600]. https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- Existing ML-KEM NTT implementation design. `docs/M32b_DESIGN.md`
- Existing ML-KEM SHAKE/CBD implementation design. `docs/M32c_DESIGN.md`
