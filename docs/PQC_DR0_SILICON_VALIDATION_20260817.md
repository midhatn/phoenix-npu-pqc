# PQC DR0 Phoenix silicon validation — 2026-08-17

> **Current release-flow correction (2026-08-18).** This dated record preserves
> its historical command and accounting language. The current canonical runner
> is now native-only and dispatches DR0 first in the five-gate DR0 → DR1 → DR2a
> → DR2b → DR2c sequence. The freshly verified current-source DR0/DR2a/DR2b/
> DR2c sub-suite is 61/61; that is not a current five-gate 94/94 claim.

## Evidence boundary

This record documents the physical Phoenix validation of the fused DR0 M33
polynomial-product graph. Its historical runner-accounting language is
superseded by the current native-only five-gate canonical runner; the evidence
scope of this dated DR0 record is otherwise unchanged.

The supplied evidence was produced on a Windows Phoenix laptop at
**2026-08-17 19:35:37 +03**. The captured terminal log is an evidence artifact;
it is not added to or modified in this source worktree.

| Evidence field | Recorded value |
|---|---|
| Command | `python tests\pqc_device_resident\test_m33_product_dr0.py` |
| Backend | `m33-dr0:silicon` |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr0_silicon_validation_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
| Directed vectors | 4 / 4 PASS |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr0_silicon_validation_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
| Deterministic random vectors | 20 / 20 PASS |
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr0_silicon_validation_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
| Terminal total | `TOTAL 24/24 PASS` |
| Exit code | 0 |
| Log name | `PQC_DR0_M33_silicon_definitive_20260817.log` |
| SHA-256 | `678F1116813F38B1356518FD601060934D8C2D5682C935FFDAD5364E0AD6CA48` |
| Log size | 2410 bytes |
| Timestamp | 2026-08-17 19:35:37 +03 |
| Host | Windows Phoenix laptop |

## Validated topology and operation

The observed native backend result applies to the fixed one-worker DR0 graph:

```text
host a --fill--> ObjectFIFO m33_dr0_in_a --\
                                                  AIE worker --> ObjectFIFO m33_dr0_out_c --drain--> host c
host b --fill--> ObjectFIFO m33_dr0_in_b --/
```

The graph has exactly two polynomial ingress transfers (`a`, `b`) and one
terminal polynomial egress (`c`). Inside the AIE design invocation it performs
`NTT(a)`, `NTT(b)`, pointwise Montgomery base multiplication, `INTT`, and
device-side canonicalization. No intermediate NTT-domain or base-product value
is drained to the host, and the one host retrieval is the terminal `c` buffer.

The 24 reported vectors comprise four directed vectors and 20 deterministic
random vectors. Their expected values are compared against the package's
independent direct O(n²) negacyclic-convolution oracle.

## Claims supported

This evidence supports only the following claim:

- The fused DR0 M33 polynomial-product graph compiled, dispatched through the
  native `m33-dr0:silicon` backend, and matched its directed and deterministic
  randomized terminal-product reference vectors on the recorded Phoenix laptop.

## Claims not supported

This record does **not** validate or claim:

- Complete ML-DSA or complete FIPS 204 conformance.
- Performance, latency, throughput, power, energy, or speedup measurements.
<!-- [CLAIM-PROVENANCE: status=HISTORICAL; source=pqc_dr0_silicon_validation_20260817; classification=SELF_REPORTED_UNVERIFIED] -->
- Constant-time execution, side-channel resistance, fault-injection resistance,
  or general cryptographic hardening.
- Host, AIE-local, DMA, ObjectFIFO, XRT, or compiled-artifact zeroization.
- Key management, secret-lifetime guarantees, production deployment approval,
  or CMVP validation/certification.
- Complete ML-DSA or any broader conclusion from DR0's narrow native gate.

## Relationship to other records

The prior M33a primitive validation is recorded separately in
[`M33_SILICON_VALIDATION_20260817.md`](M33_SILICON_VALIDATION_20260817.md).
DR0 uses production-local M33a arithmetic but this 24/24 result is specifically
for the fused terminal-only product graph described in
[`PQC_DR0_DESIGN.md`](PQC_DR0_DESIGN.md). Source and adaptation provenance is
recorded in [`PQC_DR0_PROVENANCE.md`](PQC_DR0_PROVENANCE.md).
