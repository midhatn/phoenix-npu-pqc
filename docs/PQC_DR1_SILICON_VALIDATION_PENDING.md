# DR1 Silicon Validation Record

**Status: v3 PHYSICAL PASS for the narrow DR1 milestone.**  On 2026-08-17 the
single-entrypoint v3 graph compiled, linked, placed, routed, and executed on a
physical Phoenix NPU through IRON 1.4.1.  All 33 frozen requests matched the
independent `hashlib.shake_128` / rejection-sampling oracle exactly across all
256 returned coefficient lanes.

The implementation is limited to one ML-DSA-44 `ExpandA` / `RejNTT` polynomial
per invocation.  It uses SHAKE128 over `rho || j || i`, as specified by [NIST
FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf) and [NIST
FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf).

## Definitive physical evidence

| Item | Recorded value |
|---|---|
| Backend label | `dr1-mldsa44-expanda-rejntt:silicon` |
| Physical corpus | all 16 `j/i` coordinates for `rho=bytes(range(32))`; 16 deterministic varied `rho/j/i` requests; one alternating `00/ff` boundary `rho` |
| Terminal result | `TOTAL 33/33 PASS` |
| Exact comparisons | 33 requests x 256 lanes = 8,448 exact coefficient comparisons |
| Log name | `PQC_DR1_MLDSA44_v3_physical_corpus_20260817.log` |
| Log SHA-256 | `85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E` |
| Log length | 3,382 bytes |
| Log timestamp | 2026-08-17 20:14:29 local time |
| JIT cache key | `c1b1aaa7ab02f303edff67b3` |
| Complete host log | `PQC_DR0_DR1_complete_host_zero_skip_20260817.log` |
| Complete host log SHA-256 | `2621EF2E4130003895A9DA46042CEAA232D9C11AA5D24A25D0800978283B9568` |
| Complete host log length | 10,514 bytes |
| Complete host log timestamp | 2026-08-17 20:27:27 local time |

The 33 requests executed sequentially in one Python process.  Every request
returned the terminal SUCCESS ABI, exactly 256 canonical coefficients, and the
frozen SHA-256 coefficient fingerprint for that case.  This supplies physical
evidence for repeated-request reset of the core-local producer `g_service` and
sampler `g_sampler` state in addition to exact arithmetic.

## Compiler-reported worker sizes

Peano's `llvm-size.exe -A` reported:

| Placed core | Worker confirmed in optimized IR | ELF length | `.text` | `.bss` | `.comment` | reported total |
|---|---|---:|---:|---:|---:|---:|
| `(0,2)` | `dr1_shake128_emit_next`, called eight times | 9,152 B | 6,608 B | 272 B | 197 B | 7,077 B |
| `(0,3)` | `dr1_rejntt_consume_next`, called eight times | 5,468 B | 3,328 B | 1,040 B | 197 B | 4,565 B |

The executable `.text` sections are below the project's 16 KiB per-worker
program-memory limit.  `.bss` is reported separately and is not counted as
program text.  The optimized per-core IR independently identifies core `(0,2)`
as the SHAKE worker and core `(0,3)` as the RejNTT worker.

## Recorded v1 IRON link incident (pre-execution)

The original DR1 graph used eight producer and eight sampler
`ExternalFunction(source_file=...)` declarations.  The physical Phoenix IRON
1.4.1 compile compiled each repeated source-file declaration into a separate
object; every object exported the source's eight wrappers, and `ld.lld` failed
on duplicate `dr1_shake128_emit_block_0..7` and
`dr1_rejntt_consume_block_0..7` symbols.  **No device execution occurred.**

The revised source has one exported entry point per worker source:
`dr1_shake128_emit_next` and `dr1_rejntt_consume_next`.  Each corresponding
`ExternalFunction` is declared once and called eight times by its worker.  This
addresses the observed link shape only.

## Recorded v2 physical execution mismatch

The v2 single-entrypoint design subsequently **compiled, linked, routed, and
executed** on Phoenix IRON 1.4.1.  It returned a terminal record with the valid
SUCCESS ABI shape.  It did not return the required SHAKE128/RejNTT values:
coefficient lane 0 was already wrong.  The first 16 received lanes were
`[7051560, 7489257, 7786830, 4423754, 5417319, 6241406, 4497470, 3525554,
2085872, 5419459, 1074933, 6083056, 1702221, 3509789, 3041416, 7161713]`;
the independent hashlib oracle expected
`[7905761, 7863978, 1275290, 4366663, 7850937, 4248201, 2710427, 4706185,
6565264, 5317472, 6267181, 2111275, 3977058, 3444859, 5376343, 6624750]`.
All 256 outputs were unique and the stream was not a repeated first SHAKE
block pattern.

The cause was not proven, but the host-correct table-based v2 Keccak was
suspected to be incompatible with Peano/AIE2 code generation or read-only data
handling.  V3 replaced it with an explicitly aligned 200-byte state, an
on-the-fly FIPS 202 LFSR for Iota constants, and the Rho/Pi orbit recurrence
used by the physically proven M32c algorithm shape.  The definitive v3 corpus
above validates that replacement on this Phoenix/IRON path.

## Recorded host and source checks (2026-08-17)

The following off-hardware checks completed against the v3 LFSR/orbit source
in the development workspace:

| Check | Result |
|---|---|
| DR1 independent-reference, 33-case compiled C++ exact-output corpus, repeated/interrupted-request reset, sampler corruption, malformed-ABI, freeze/drain, and static-contract tests | `24 passed`, no skips on Windows with MSYS2 UCRT64 `g++ 16.2.0` |
| Complete combined DR0, DR1, M33 native-runner, and validation-policy host suite | `56 passed`, no skips |
| Available existing DR0 unit/contracts plus M33 native-runner contracts | `21 passed` |
| Python `compileall` and C++ `-Wall -Wextra -Werror -pedantic -fsyntax-only` | passed |
| C++ exact-output harness with `-fsanitize=undefined` across the full 33-case corpus | passed |
| `git diff --check` (working and staged) | passed |
| `run_all_silicon_tests.py` SHA-256 against `HEAD` | identical |

The 33 test-only coefficient SHA-256 fixtures live beside the independent
oracle/harness; they are compact tripwires against a simultaneous parser and
oracle change, not a standards vector set.

The complete 56-test command above does not include the five standalone
`tests/m33_mldsa` scripts.  Those scripts require the separate `dilithium-py`
dependency and remain outside this narrowly scoped DR1 validation record.

## Claim boundary and remaining evidence

This record establishes physical exact-output execution only for the narrow
DR1 operation and fixed successful-request corpus described above.  The graph
retains exactly two host ingress FIFOs, one internal XOF FIFO, one terminal
result FIFO, two host fills, one terminal drain, and no host/reference fallback.
DR1 remains excluded from the canonical 34-entry silicon runner.

The physical corpus did not inject malformed descriptors or corrupted internal
tokens; those fail-closed paths remain host-compiled/source-contract evidence.
Stack usage, FIFO bank/depth reports, toolchain component versions beyond IRON
1.4.1, and generated xclbin identity were not captured in this record.

There is no claim of complete FIPS 204 device residency or conformance, full
ML-DSA key generation/signing/verification, performance or throughput
improvement, constant-time behavior, secure zeroization, side-channel
resistance, CMVP validation, or CMVP certification.
