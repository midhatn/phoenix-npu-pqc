# PQC DR2c Design: ML-KEM-512 K-PKE.KeyGen Terminal Row

**Status:** a narrow physical `TOTAL 11/11 PASS` record is retained for the
terminal-row scope, with repeated `22/22` execution recorded separately. DR2c
is a narrow terminal-only subgraph toward K-PKE.KeyGen; it is **not K-PKE KeyGen**,
ML-KEM KeyGen, or a complete ML-KEM operation. See the dated
[physical validation record](PQC_DR2C_SILICON_VALIDATION_PENDING.md) for
evidence scope and provenance limitations.

## Scope

DR2c evaluates one requested ML-KEM-512 row, `row_index` 0 or 1, after its
caller has already produced the FIPS 203 KeyGen seeds `rho` and `sigma`. The
public API packs them as `rho || sigma` into one 64-byte seed DMA ingress. It keeps both matrix elements, the two secret NTT polynomials, the selected error
NTT polynomial, both `MultiplyNTTs` products, and the accumulator within the
AIE graph. Its only successful output is the canonical 256-lane
$\widehat t[\mathrm{row}]$:

$$
\widehat t[i]=\mathrm{MultiplyNTTs}(\widehat A[i,0],\widehat s[0])+
\mathrm{MultiplyNTTs}(\widehat A[i,1],\widehat s[1])+\widehat e[i]\pmod{3329}.
$$

This is the existing FIPS 203 K-PKE.KeyGen relation, specialized to one
ML-KEM-512 row; no new publication mathematics is required beyond the
authoritative equation in [NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf).

The expansion worker derives `A_hat[row,0]` and `A_hat[row,1]` with bounded
five-block `SampleNTT(rho || column || row)`, and derives
`NTT(CBD3(SHAKE256(sigma || counter)))` for counters 0, 1, and `row+2`. The
five-block bound is the existing DR2a project choice aligned to FIPS 203
Appendix B; a limit error has fixed zero terminal payload.

## Fixed ABI v1

All multi-byte fields are little-endian.

| Item | Size | Layout |
|---|---:|---|
| packed seeds | 64 B | exactly `rho[32] || sigma[32]`; the sole seed DMA ingress |
| descriptor | 16 B | v1; opcode `0x23`; parameter `0x52`; flags 0; row `0..1`; eta 3; SampleNTT blocks 5; reserved 0; u32 request ID; four zero bytes |
| private row token | 2,576 B | request ID; status; row; seven zero reserved bytes; five canonical 256-lane NTT polynomials: `A0`, `A1`, `s0`, `s1`, `e[row]` |
| terminal result | 528 B | magic `0x4332524d`; echoed request ID; status; coefficient count; echoed row; zero reserved; one canonical `t_hat[row]` |

The IRON graph has exactly two host ingress ObjectFIFOs (`dr2c_seeds`,
`dr2c_descriptor`), one internal ObjectFIFO (`dr2c_row_token`), and one
terminal ObjectFIFO (`dr2c_result`): four ObjectFIFOs total. Runtime has
exactly two fills and one drain. Only `result_t.to("cpu")` occurs after dispatch.

## Failure, residency, and reset

The expansion worker validates the descriptor before deriving anything. It
writes `BAD_DESCRIPTOR` or `LIMIT_EXCEEDED` into the private token, with no
polynomial data. The accumulation worker validates token metadata and every
lane before multiplication. It returns only `OK`, `LIMIT_EXCEEDED`,
`BAD_DESCRIPTOR`, or `BAD_TOKEN`, always with an all-zero terminal payload on
an error.

SHAKE state, PRF bytes, matrix candidates, CBD coefficients, all five private
polynomials, products, accumulator scratch, and the consumed private token are
cleared before workers return. The terminal result contains no seed, matrix,
secret, error, PRF stream, or product. Request-local stacks and the explicit
clears support repeated-request reset tests, but this is not a claim of
hardware-remanence resistance or side-channel security.

## Verification boundary

`tests/pqc_device_resident/dr2c_reference.py` independently uses `hashlib` for
SHAKE, a standalone FIPS 203 candidate parser, LSB-first CBD3, direct
FIPS 203 NTT, and direct `MultiplyNTTs`; it imports no DR2c production module.
The compiled production harness builds the two production C++ workers under
strict C++17 flags and compares every terminal lane against that independent
reference. It also tests malformed descriptor/token paths and repeated calls.
Host compilation is not physical proof.

The native gate is intentionally separate and has no fallback. Any new physical
claim requires separately authorized Phoenix native evidence. The current
`run_all_silicon_tests.py` is native-only and invokes this gate fifth; the
historical host-forwarder description is superseded.

## References

- NIST FIPS 203, Algorithms 7–13, §2.4.7, §4.1, Appendix B, and Table 2. https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf
- NIST FIPS 202, SHAKE128, SHAKE256, and Keccak-f[1600]. https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- DR2a matrix sampler design. `docs/PQC_DR2A_DESIGN.md`
- DR2b noise-to-NTT design. `docs/PQC_DR2B_DESIGN.md`
