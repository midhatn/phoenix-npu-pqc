# PQC device-residency research roadmap

**Status date:** 2026-08-18
**Purpose:** claim-safe research sequencing for a long-term, fully device-resident PQC target. This is a research roadmap, not a delivery schedule, implementation claim, certification plan, or authorization to run hardware.

## Governing completion rule

The long-term target is **100% NPU-resident execution** for:

- all FIPS 202 SHA-3/SHAKE operations required by the supported PQC flows;
- every FIPS 203 ML-KEM parameter set (ML-KEM-512, ML-KEM-768, ML-KEM-1024) and every specified operation (KeyGen, Encaps, Decaps); and
- every FIPS 204 ML-DSA parameter set (ML-DSA-44, ML-DSA-65, ML-DSA-87) and every specified operation (KeyGen, Sign, Verify).

“100% NPU-resident” means that the cryptographic operation’s specified cryptographic computation, intermediate state, sampling, transforms, packing/encoding, comparison, rejection/control flow, and final validation are resident in the NPU graph. Host work may submit public inputs and retrieve the final public API result, but may not supply a cryptographic fallback, compute an intermediate, or repair a device result. Each operation must have an independent oracle, fail-closed error handling, reproducible build/provenance, and a separately recorded physical exact-output gate.

FIPS 205 and FIPS 206 are **unnumbered future work**. This roadmap deliberately assigns no DR number, scope, schedule, or completion claim to them.

## Research-decision sequence

| Decision record | Scope and evidence boundary | Recorded state | Exit condition before advancing |
|---|---|---|---|
| **DR0** | One fused ML-DSA ring-product primitive on one Phoenix AIE2 worker. | **Merged and physically validated.** DR0 is included in PR #8 / commit `7b38973789fafb950a26551bc947f4fcaa91ec25`; the narrow native record is 24/24 pass. | Retained as a proven primitive; no broader ML-DSA-residency claim follows from it. |
| **DR1** | ML-DSA-44 ExpandA / rejection-sampling / NTT path, with a bounded device/host ABI. | **Merged and physically validated.** DR1 is included in PR #8 / commit `7b38973789fafb950a26551bc947f4fcaa91ec25`; the narrow native record is 33/33 pass. | Retained as a proven primitive/path; no complete FIPS 204 or device-resident ML-DSA claim follows from it. |
| **DR2a** | ML-KEM-512 `SampleNTT(SHAKE128(rho || j || i))` for one matrix polynomial. | **Narrow physical pass.** The record anchors 13/13 and a repeated 26/26 run. | Preserve the bounded ABI, oracle, and fail-closed rule; do not recast as KeyGen. |
| **DR2b** | ML-KEM-512 CBD3/NTT seed-noise building block used as the physically passed comparator for DR2d investigation. | **Narrow physical pass.** The DR2d audit records a passed 13-vector DR2b cache comparison. | Retain the passed artifact for read-only comparison; it is not integrated K-PKE.KeyGen. |
| **DR2c** | One terminal ML-KEM-512 K-PKE.KeyGen `t_hat` row under a two-host-input ABI. | **Narrow physical pass.** The follow-up record anchors 11/11 and repeated 22/22 execution. | Preserve the exact row boundary; `G(d || k)`, both-row scheduling, serialization, and lifecycle zeroization remain outside DR2c. |
| **DR2d** | Integrated five-worker ML-KEM-512 K-PKE.KeyGen research candidate: W0 seed/noise, W1/W3 matrix expansion, W2/W4 accumulation, then serializer. | **Physical fail.** Compile-only/store/placement review passed, but the anchored backend returned `TOTAL 0/25 FAIL`, exit 1. One authorized W0 `tcId-01` diagnostic capture completed; no further hardware action is authorized. | Expert resolution of the systematic semantic mismatch; a clean, independently checked integrated DR2 physical corpus; retained provenance and exact-output evidence; explicit approval to proceed. |
| **DR2 (integrated)** | The first fully integrated ML-KEM KeyGen research gate. | **Blocked.** DR2a/DR2b/DR2c passes do not close DR2d or integrated KeyGen. | DR2d must be completed as above. No DR3 work may start before integrated DR2 is complete and its decision record is closed. |
| **DR3** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | Integrated DR2 completion and a new, reviewable scope decision. |
| **DR4** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR3 closure plus a new scope decision. |
| **DR5** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR4 closure plus a new scope decision. |
| **DR6** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR5 closure plus a new scope decision. |
| **DR7** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR6 closure plus a new scope decision. |
| **DR8** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR7 closure plus a new scope decision. |
| **DR9** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR8 closure plus a new scope decision. |
| **DR10** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR9 closure plus a new scope decision. |
| **DR11** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR10 closure plus a new scope decision. |
| **DR12** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR11 closure plus a new scope decision. |
| **DR13** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR12 closure plus a new scope decision. |
| **DR14** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR13 closure plus a new scope decision. |
| **DR15** | Reserved; no implementation scope starts while DR2 is blocked. | **Not started.** | DR14 closure plus a new scope decision. |

## Current stop state

1. DR0 and DR1 were merged by PR #8 at `7b38973789fafb950a26551bc947f4fcaa91ec25`; they are not pending work.
2. DR2a, DR2b, and DR2c are **narrow physical passes**, each bounded by its own ABI and corpus.
3. DR2d is an **integrated physical fail**, not a partial pass. Its 0/25 outcome blocks the integrated DR2 decision.
4. No activity may be described as DR3 or later research until integrated DR2 completion is recorded. The reservation of DR3–DR15 is intentionally not a promise of scope, date, staffing, or outcome.
5. The present expert handoff and immutable evidence inventory are [`PQC_DR2_EXPERT_ESCALATION_20260818.md`](PQC_DR2_EXPERT_ESCALATION_20260818.md) and [`pqc_dr2_evidence_20260818/README.md`](pqc_dr2_evidence_20260818/README.md). They do not authorize hardware execution.

## Claim boundaries

This roadmap does **not** claim complete ML-KEM, complete ML-DSA, FIPS conformance, constant-time behavior, secure zeroization, side-channel resistance, performance, CMVP validation, certification, a production release, or a driver/toolchain root cause. The existing v1 scope remains a mixture of native primitive gates and host/NPU compositions; see [`PQC_COMPLETE_V1.md`](PQC_COMPLETE_V1.md).

## References

- NIST FIPS 202, *SHA-3 Standard*: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- NIST FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf
- NIST FIPS 204, *Module-Lattice-Based Digital Signature Standard*: https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf
- MLIR-AIE 1.4.1 documentation: https://xilinx.github.io/mlir-aie/1.4.1/
- Xilinx mlir-aie pinned commit: https://github.com/Xilinx/mlir-aie/commit/3ca0193cea9e2c39ec670a65f93e1dd43c969f22
- LLVM-AIE: https://github.com/Xilinx/llvm-aie
- XRT: https://github.com/Xilinx/XRT
- AMD XDNA kernel documentation: https://docs.kernel.org/accel/amdxdna/amdnpu.html
