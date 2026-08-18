# Security policy

## Reporting a vulnerability

If you discover a vulnerability in Phoenix NPU PQC, do not open a public issue.
Use GitHub Private Vulnerability Reporting or email
**medhat.nashar@gmail.com** with the subject
`[phoenix-npu-pqc SECURITY]`.

Include the affected file or component, a minimal reproduction, impact,
environment details, and any relevant host-safe or native evidence. Do not
attach secrets, private keys, sensitive test vectors, or unredacted device
captures to a public report.

## Scope

In scope:

- FIPS 202/203/204 implementation and validation defects in
  `phoenix_sdr_dsp/pqc/` and PQC test code.
- Host-side validation, serialization, provenance, checksum, and
  fail-closed behavior defects.
- Native MLIR-AIE / XRT integration defects that could corrupt buffers,
  misreport a result, or obscure a failed device dispatch.
- Supply-chain or integrity issues in current metadata, installer code, or
  the protected evidence inventory.

Out of scope:

- Security defects in AMD's XDNA driver, MLIR-AIE, LLVM-AIE, or XRT
  themselves; report those to their upstream projects.
- Claims based only on a historical physical log without a reproducible
  affected repository component.
- Requests to interpret historical research evidence as production
  certification.

## Research-use and cryptographic-security boundary

This repository is research infrastructure, not a production cryptographic
module. It does not claim FIPS or CMVP conformance, constant-time behavior,
side-channel resistance, secure zeroization, key-management suitability, or
production readiness. Host-safe tests, compile-only output, and historical
native transcripts are different evidence classes and must not be promoted into
one another.

The protected `docs/pqc_dr2_evidence_20260818/` bundle is immutable historical
evidence. It includes machine-specific paths and diagnostic material; do not
rewrite it to redact or “fix” it. Restrict access appropriately and publish a
separate, reviewed redacted derivative if disclosure is required.

## Supported versions

Only the current `main` branch is maintained. Historical evidence records are
retained for provenance and are not retroactively changed as a security fix.

| Version | Supported |
| --- | --- |
| `main` | Yes |

## Responsible research

Good-faith research that avoids privacy violations, destruction of data, and
disruption of systems is welcome. Test only hardware and accounts you own or
are authorized to use, and allow reasonable time for remediation before public
disclosure.
