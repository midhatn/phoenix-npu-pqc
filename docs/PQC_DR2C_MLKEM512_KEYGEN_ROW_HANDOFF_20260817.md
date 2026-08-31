# DR2c ML-KEM-512 K-PKE.KeyGen Row Handoff

Date: 2026-08-17

## Corrected scope

DR2c is a terminal-only resident ML-KEM-512 K-PKE.KeyGen `t_hat` row. It is a
narrow graph milestone and is not complete K-PKE.KeyGen, ML-KEM KeyGen, or
complete ML-KEM. This correction satisfies the Phoenix/native strict two-input
DMA/host-ingress limit.

## Incremental files

- `phoenix_sdr_dsp/pqc/dr2c_mlkem512_keygen_row_abi.py`
- `phoenix_sdr_dsp/pqc/dr2c_mlkem512_keygen_row_graph.py`
- `phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_expand.cc`
- `phoenix_sdr_dsp/pqc/kernels/dr2c_mlkem512_keygen_row_accumulate.cc`
- `tests/pqc_device_resident/dr2c_reference.py`
- `tests/pqc_device_resident/test_dr2c_mlkem512_keygen_row.py`
- `tests/pqc_device_resident/test_dr2c_mlkem512_keygen_row_silicon.py`
- `tests/test_pqc_dr2c_contract.py`
- `docs/PQC_DR2C_DESIGN.md`
- `docs/PQC_DR2C_SILICON_VALIDATION_PENDING.md`

`run_all_silicon_tests.py`, all existing DR0/DR1/DR2a/DR2b files, and the
publication mathematics section remain unchanged. The row equation and NTT
representation are already authoritatively documented in
`docs/MILESTONES_AND_MATHEMATICS.md`.

## Two-input architecture and ABI

The public Python API remains:

```python
run_mlkem512_keygen_row(rho, sigma, row_index, request_id)
```

It validates both 32-byte values before native runtime loading, concatenates
`rho || sigma` into one immutable 64-byte `dr2c_seeds` ingress record, and
builds the existing strict 16-byte descriptor. These are the only two host
inputs.

The graph has exactly four ObjectFIFOs:

1. `dr2c_seeds`: 64-byte host ingress, `rho[32] || sigma[32]`.
2. `dr2c_descriptor`: 16-byte host ingress.
3. `dr2c_row_token`: private 2,576-byte internal token containing five NTT
   polynomials.
4. `dr2c_result`: 528-byte terminal output.

Runtime performs exactly two fills and one drain. `result_t.to("cpu")` is the
sole post-dispatch host transfer.

The expansion worker splits the device-local packed buffer into `rho` and
`sigma`, validates the descriptor, derives both `SampleNTT` matrix polynomials
for the requested row, and derives `s_hat[0]`, `s_hat[1]`, and `e_hat[row]`
through SHAKE256/PRF/CBD3/NTT. The accumulator validates the private token,
performs both FIPS 203 `MultiplyNTTs` products plus modular accumulation, and
returns only canonical `t_hat[row]`.

The terminal ABI is unchanged: magic `0x4332524d`, echoed request ID, status,
coefficient count, echoed row, reserved zero, and 256 canonical residues. On
`LIMIT_EXCEEDED`, `BAD_DESCRIPTOR`, or `BAD_TOKEN`, it requires count zero and
a fixed all-zero terminal payload. No host SHAKE, sampling, NTT, multiplication,
or reference fallback exists. Scratch, private polynomials, PRF/state buffers,
and the consumed token are explicitly cleared as before.

## Validation completed locally

- Strict production C++17 compilation passed using shared PIC, `-O2`, `-Wall`,
  `-Wextra`, `-Werror`, and `-pedantic`.
- Focused DR2c reference, ABI, compiled-harness, and contract suite: **14 tests
  passed**.
- Ruff passed on every DR2c Python source/test file.
- `git diff --check` passed.
- Packed-seed ABI assertion passed: `rho || sigma` is exactly 64 bytes.
- Static stale-text scan passed for the former separate-ingress FIFO names and
  superseded ingress-count wording.
- The native-only gate was run off hardware and correctly reported
  `dr2c-mlkem512-keygen-row:unavailable` with exit code 2. This is unavailable,
  not a physical result.

The test-only direct oracle imports no DR2c production module. It independently
uses SHAKE128/SHAKE256, SampleNTT candidate parsing, CBD3, FIPS 203 NTT, and
`MultiplyNTTs`; the compiled production harness compares every terminal lane
across 11 frozen requests and tests malformed descriptor/token paths and
repeated requests in one compiled process.

## Remaining native risks and gate

No Phoenix physical compilation, placement/routing, runtime execution,
program-size measurement, or physical PASS has been claimed. Native validation
must verify the two input shim routes, the sole result route, absence of a shim
route for the private token, ObjectFIFO placement/depth/banks, instruction/data
and 16 KiB stack fit, and repeated in-process execution. The current
five-SHAKE128-block SampleNTT bound remains the prior DR2a project choice.
`G(d || k)`, scheduling both rows, key serialization, and lifecycle zeroization
remain outside DR2c.

Exact native PowerShell command:

```powershell
py .\tests\pqc_device_resident\test_dr2c_mlkem512_keygen_row_silicon.py
```

A native runtime absence must return exit 2; a real native run must show the
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr2c_mlkem512_keygen_row_handoff_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
silicon backend and `TOTAL 11/11 PASS`. Repeat all 11 requests twice in one
process and retain full native output, compilation/memory reports, FIFO
placement, and DMA-route evidence before changing the pending physical record.

## Patch applicability

The saved incremental patch contains only the ten DR2c add-file diffs above;
it does not modify any pre-existing repository file. It was checked by applying
it in an isolated local worktree. It can apply after the requested lineage as
long as those DR2c paths do not already exist.
