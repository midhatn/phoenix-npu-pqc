# DR2a Silicon Validation Record

> **Current release-flow correction (2026-08-18).** DR2a is now the third gate
> in the native-only canonical `run_all_silicon_tests.py` sequence. The freshly verified retained
> current-source DR0/DR2a/DR2b/DR2c sub-suite is 61/61; it does not include a
> fresh DR1 execution and must not be called a current 94/94 result.

**Status: PHYSICAL PASS for the narrow DR2a milestone.**  On 2026-08-17 the
two-worker bounded SHAKE128/SampleNTT graph compiled, linked, placed, routed,
and executed on a physical Phoenix NPU through IRON 1.4.1.  All 13 frozen
requests matched the independent `hashlib.shake_128` / FIPS 203 parser oracle
across all 256 returned coefficient lanes.

## Validated scope

The graph accepts `rho[32]`, ML-KEM-512 coordinates `(j,i)` in `0..1`, and a
request ID.  It produces one terminal 256-lane `int16` polynomial for

$$
\mathrm{SampleNTT}(\mathrm{SHAKE128}(\rho\mathbin\Vert j\mathbin\Vert i))
$$

or a fixed terminal error.  It schedules five 168-byte SHAKE128 blocks, which
is 280 three-byte candidate iterations, the bounded minimum identified by
[FIPS 203 Appendix B](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf).

## Definitive physical evidence

| Item | Recorded value |
|---|---|
| Backend label | `dr2a-mlkem512-samplentt:silicon` |
| Physical corpus | all four `j/i` coordinates for `rho=bytes(range(32))`; eight deterministic varied-rho requests; one alternating `00/ff` boundary rho |
| Terminal result | `TOTAL 13/13 PASS` |
| Exact comparisons | 13 requests x 256 lanes = 3,328 exact coefficient comparisons |
| Repeated-operation result | two complete corpora in one Python process; 26/26 requests passed; `first=0, second=0` |
| Definitive log | `PQC_DR2A_MLKEM512_SAMPLENTT_physical_20260817.log`, 865 bytes, 2026-08-17 20:50:33 local time |
| Complete DR0/DR1/DR2a host log | `PQC_DR0_DR1_DR2A_complete_host_zero_skip_20260817.log`, 14,798 bytes, 2026-08-17 20:53:11 local time |
| Complete host result | 78 tests passed, zero skips, exit code 0 |
| Source revision before local DR2a patch | `b5770127f448a096d38e412f6a4d5e92e92f7ed0` |
| JIT cache key | `c65a53d2c8de882f9a5dc7d9` |
| Generated xclbin | `final.xclbin`, 18,520 bytes |
| PDI UUID | `dff7cf7e-0931-4fd5-b1e3-55f43b342e83` |

The repeated run reused the cached program and exercised producer and sampler
state reset across 26 sequential native requests.  Every request returned the
terminal success ABI with 256 canonical coefficients.

## Compiler-reported program size and placement

Peano's `llvm-size.exe -A` and the optimized per-core IR reported:

| Placed core | Worker and scheduled calls | ELF length | `.text` | `.bss` | Stack reservation | Reported total |
|---|---|---:|---:|---:|---:|---:|
| `(0,2)` | `dr2a_shake128_emit_next`, five calls | 8,748 B | 6,192 B | 272 B | 16 KiB (`0x4000`) | 6,661 B |
| `(0,3)` | `dr2a_samplentt_consume_next`, five calls | 5,132 B | 2,976 B | 524 B | 16 KiB (`0x4000`) | 3,697 B |

The executable `.text` sections are below the project's 16 KiB per-worker
program-text gate.  The linker scripts record program regions of `0x20000`
bytes and explicit `0x4000` stack reservations for both cores.

## FIFO allocation and routes

Placed `aie.mlir` contains exactly four depth-two ObjectFIFOs:
`dr2a_rho` (32 bytes), `dr2a_descriptor` (16 bytes),
`dr2a_xof_block` (180 bytes), and `dr2a_result` (528 bytes).
`input_with_addresses.mlir` records:

- the two internal XOF buffers on tile `(0,2)`, banks 1 and 2, at addresses
  16,384 and 32,768;
- the two terminal-result buffers on tile `(0,3)`, banks 1 and 2, at addresses
  16,384 and 32,768;
- descriptor buffers on tile `(0,2)`, banks 2 and 3;
- rho buffers on tile `(0,2)`, banks 3 and 1;
- shim MM2S channel 0 for the descriptor and channel 1 for rho;
- shim S2MM channel 0 for the only terminal result; and
- runtime DMA lengths of 16 and 32 bytes for the two fills and 528 bytes for
  the one terminal drain.

## Reproduction procedure

1. Use the pinned Phoenix XDNA1 / IRON 1.4.1 / XRT environment.
2. Confirm the worktree and record the source revision and dirty/clean state.
3. Run the targeted host checks before native compilation:

   ```text
   ruff check phoenix_sdr_dsp/pqc/dr2_mlkem512_samplentt_abi.py \
     phoenix_sdr_dsp/pqc/dr2_mlkem512_samplentt_graph.py \
     tests/pqc_device_resident/dr2a_reference.py \
     tests/pqc_device_resident/test_dr2_mlkem512_samplentt.py \
     tests/pqc_device_resident/test_dr2a_mlkem512_samplentt_silicon.py \
     tests/test_pqc_dr2a_contract.py
   python -m unittest \
     tests.pqc_device_resident.test_dr2_mlkem512_samplentt \
     tests.test_pqc_dr2a_contract
   ```

4. Run the native-only gate:

   ```text
   python tests/pqc_device_resident/test_dr2a_mlkem512_samplentt_silicon.py
   ```

   A missing runtime must print `Backend: dr2a-mlkem512-samplentt:unavailable`
   and return status 2; it is not a pass.  A physical success must print the
   silicon backend and the anchored `TOTAL 13/13 PASS`.
5. Compare all four coordinates under `rho=bytes(range(32))`, the eight
   deterministic varied-rho cases, and the alternating `00/ff` boundary rho
   against the independent `hashlib.shake_128`/FIPS-203 parser oracle.
6. Repeat the full corpus twice in one Python process to exercise reset of the
   producer and sampler state.
7. Retain compiler and placement evidence, including program size, stack,
   `.bss`, FIFO depth/bank, routes, generated xclbin identity, and placed-core
   records.
8. On the physical machine, exercise malformed descriptor and internal-token
   corruption only if the toolchain permits controlled injection.  Verify five
   tokens are always drained and the only terminal failures have zero payload.

## Current off-hardware evidence

The implementation has a compiled production-kernel harness.  It builds
`dr2_mlkem512_shake128_service.cc` and `dr2_mlkem512_samplentt.cc` together,
checks the complete five-block SHAKE stream and 256 returned coefficients
against an independent `hashlib` oracle, verifies repeated-request state reset,
injects malformed token headers, and injects a fully rejected five-block
stream to force `LIMIT_EXCEEDED`.  These results are host evidence only and do
not establish placement, routing, AIE code generation, or execution on a
Phoenix NPU.  The final combined DR0/DR1/DR2a host suite ran all 78 tests with
the MSYS2 UCRT64 compiler available, so no compiled production-kernel harness
test was skipped.

The historical statement above about canonical-runner integration is superseded
by the current native-only canonical runner. This record remains narrow DR2a
evidence, not integrated KeyGen evidence.

## Claim boundary

This record establishes physical exact-output execution only for one bounded
ML-KEM-512 SampleNTT polynomial per invocation under the fixed successful
corpus.  The physical corpus did not inject malformed descriptors or corrupted
internal tokens; those fail-closed paths remain compiled host-harness and
source-contract evidence.

Do not claim complete K-PKE KeyGen, complete ML-KEM device residency or
conformance, performance, constant-time behavior, secure zeroization,
side-channel resistance, CMVP validation, or certification.
