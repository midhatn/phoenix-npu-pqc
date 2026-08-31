# DR2b Silicon Validation Record

> **Current release-flow correction (2026-08-18).** DR2b is now the fourth
> gate in the native-only canonical sequence. The freshly verified retained
> current-source DR0/DR2a/DR2b/DR2c sub-suite is 61/61, not a current 94/94
> result.

**Status: PHYSICAL PASS for the narrow DR2b milestone.**  On 2026-08-17 the
two-worker SHAKE256/CBD3/NTT graph compiled, linked, placed, routed, and
executed on a physical Phoenix NPU through IRON 1.4.1. All 13 frozen requests
matched the independent `hashlib.shake_256`, CBD3, and direct FIPS 203 NTT
oracle across all 256 returned coefficient lanes.

## Validated scope

DR2b is only one terminal-only ML-KEM-512 $\eta_1=3$ noise polynomial:
SHAKE256 PRF from `sigma || counter`, then CBD3, then FIPS 203 NTT. The only
host-visible successful value is the final 256-lane NTT polynomial.

$$
\widehat f=\mathrm{NTT}\left(
\mathrm{SamplePolyCBD}_3\left(
\mathrm{SHAKE256}(\sigma\mathbin\Vert b,1536)
\right)\right).
$$

The 192-byte PRF stream and coefficient-domain CBD polynomial remain
device-local. The successful corpus covers all four ML-KEM-512 KeyGen noise
counters, eight deterministic varied-seed requests, and one alternating
`00/ff` boundary seed.

## Definitive physical evidence

| Item | Recorded value |
|---|---|
| Backend label | `dr2b-mlkem512-noise-ntt:silicon` |
| Physical corpus | counters 0 through 3 for `sigma=bytes(range(32))`; eight deterministic varied-sigma requests; one alternating `00/ff` boundary sigma |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr2b_silicon_validation_pending; classification=SELF_REPORTED_UNVERIFIED] -->
| Terminal result | `TOTAL 13/13 PASS` |
| Exact comparisons | 13 requests x 256 lanes = 3,328 exact coefficient comparisons |
| Repeated-operation result | two complete corpora in one Python process; 26/26 requests passed; `first=0, second=0` |
| Definitive log | `PQC_DR2B_MLKEM512_NOISE_NTT_physical_20260817.log`, 856 bytes, 2026-08-17 21:29:13 local time |
| Complete DR0/DR1/DR2a/DR2b host log | `PQC_DR0_DR1_DR2A_DR2B_complete_host_zero_skip_20260817.log`, 17,492 bytes, 2026-08-17 21:31:56 local time |
| Complete host result | 92 tests passed, zero skips, exit code 0 |
| Ordered validated source | DR2a `99c80ac`; DR2b `8b1bff2` |
| JIT cache key | `4311961d4f3a43976aa5a60d` |
| Generated xclbin | `final.xclbin`, 17,288 bytes |
| Generated PDI | `main.pdi`, 10,832 bytes |
| PDI UUID | `d420b963-9fb7-47c3-9fda-a9a55ae3ed2d` |
| Partition | four columns beginning at column 0; DPU kernel ID `0x901` |

The repeated run reused the cached native program and exercised producer and
consumer state reset across 26 sequential requests. Every request returned the
terminal success ABI with 256 canonical coefficients.

The ordered DR2a and DR2b commits were reconstructed on top of merged DR0/DR1
commit `7b38973`. All ten DR2a files and all eleven DR2b/mathematics files were
byte-compared with their preserved physical-validation snapshots before the
final 92-test host gate; both equivalence checks returned exit code 0.

## Compiler-reported program size and memory

Peano's `llvm-size.exe -A` and the generated linker scripts reported:

| Placed core | Worker | ELF length | `.text` | `.data` | Stack reservation | Reported section total |
|---|---|---:|---:|---:|---:|---:|
| `(0,2)` | SHAKE256 PRF producer | 7,264 B | 5,056 B | 0 B | 16 KiB (`0x4000`) | 5,253 B |
| `(0,3)` | CBD3 and NTT consumer | 5,908 B | 3,424 B | 256 B | 16 KiB (`0x4000`) | 3,877 B |

Both linker scripts provide `0x20000`-byte program regions. Core `(0,2)` has a
data region beginning at `0x7C030` with length `0x3FD0`; core `(0,3)` has a
data region beginning at `0x7C008` with length `0x3FF8`. Both scripts assign
`.data`, `.rodata`, and `.bss` to their declared data regions.

## FIFO allocation and routes

Generated `aie.mlir` contains exactly four depth-two ObjectFIFOs:
`dr2b_sigma` (32 bytes), `dr2b_descriptor` (16 bytes), `dr2b_prf_token`
(208 bytes), and `dr2b_result` (528 bytes). The placed
`input_with_addresses.mlir` records:

- sigma buffers on tile `(0,2)`, banks 3 and 1, at addresses 49,152 and
  16,608;
- descriptor buffers on tile `(0,2)`, banks 2 and 3, at addresses 32,992 and
  49,184;
- internal PRF-token buffers on tile `(0,2)`, banks 1 and 2, at addresses
  16,384 and 32,768;
- terminal-result buffers on tile `(0,3)`, banks 1 and 2, at addresses 16,384
  and 32,768;
- shim MM2S channel 0 for the descriptor and channel 1 for sigma; and
- shim S2MM channel 0 for the only terminal result.

The internal PRF token has no shim route. This placement supports the narrow
claim that the PRF bytes and CBD-domain coefficients remain within the AIE
graph, while only the terminal NTT result returns to the host.

## Reproduction procedure

1. Run the host gate first:

   ```text
   python -m unittest tests.pqc_device_resident.test_dr2b_mlkem512_noise_ntt tests.test_pqc_dr2b_contract
   ```

2. Run the native-only gate:

   ```text
   python tests/pqc_device_resident/test_dr2b_mlkem512_noise_ntt_silicon.py
   ```

   A missing runtime must print `Backend: dr2b-mlkem512-noise-ntt:unavailable`
   and return exit status 2. That is unavailable, not a pass. A successful
   <!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr2b_silicon_validation_pending; classification=SELF_REPORTED_UNVERIFIED] -->
   native run must show the silicon backend and `TOTAL 13/13 PASS`.

3. Retain the exact source revision, dirty state, full native output, JIT cache
   key, generated xclbin/PDI identity, repeated in-process corpus result,
   compiler-reported program size for both workers, stack reservations,
   `.text`/`.bss`, FIFO placement/depth/banks, and DMA routes.

4. Repeat all 13 requests twice in the same process to exercise request-state
   reset.
5. Retain `llvm-size` output, linker-memory regions, ObjectFIFO placement and
   bank addresses, shim routes, xclbin/PDI identity, and partition metadata.
6. If controlled physical injection is possible, demonstrate BAD_DESCRIPTOR
   and BAD_TOKEN with the fixed zero terminal payload.

## Current host evidence

The compiled production harness compares all 192 internal PRF bytes and all
256 terminal NTT lanes against its independent oracle. It also checks
repeated-request reset, malformed descriptors and tokens, and fixed-zero error
payloads. Those checks are host evidence and do not enlarge the physical
claim. The final combined DR0/DR1/DR2a/DR2b suite ran 92 tests with the
production C++ harnesses available, zero skips, and exit code 0.

The historical statement above is superseded by the current five-gate
native-only canonical runner. DR2b remains a narrow terminal result and does
not close integrated DR2.

## Claim boundary

This record establishes physical exact-output execution only for one
ML-KEM-512 $\eta_1=3$ noise-to-NTT polynomial per invocation under the fixed
successful corpus. The physical corpus did not inject malformed descriptors
or corrupted internal tokens; those fail-closed paths remain compiled
host-harness and source-contract evidence.

It is not complete K-PKE.KeyGen and not complete ML-KEM. Do not claim complete FIPS 203 conformance, performance, constant-time behavior, secure zeroization, side-channel resistance, CMVP validation, or certification.
