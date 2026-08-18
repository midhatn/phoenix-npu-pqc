# Third-party notices and provenance

## Scope

The root [`LICENSE`](LICENSE) is Apache License 2.0 for original project files
that do not declare a different license. A file-level SPDX identifier controls
when it differs. This notice records known provenance and is not a substitute
for a legal review of line-for-line transliterations or future redistribution.

## Apache-2.0 source files

Most native DR1–DR2d and M33 kernel files carry
`SPDX-License-Identifier: Apache-2.0`. The full Apache License 2.0 text is
bundled at [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt). File-level SPDX
identifiers remain authoritative when they differ from the project default.

`tests/m32_mlkem/kpke_kernel.cc` remains explicitly MIT because its header
describes a line-for-line pq-crystals Kyber reference transliteration. Its
file-level SPDX identifier must be retained. The previously applicable project
MIT text is preserved at [`LICENSES/MIT.txt`](LICENSES/MIT.txt); exact upstream
revision and notice verification remains required before a formal
redistribution claim.

## Cryptographic reference provenance requiring retention review

Several test and reference sources describe themselves as a direct or
line-for-line transliteration of pq-crystals reference implementations. Before
redistributing those files as a release artifact, verify the exact upstream
revision, upstream license/notice obligations, and whether the local change is
a derivative work:

| Local material | Declared/source provenance | Canonical URL |
| --- | --- | --- |
| ML-KEM test/reference material | pq-crystals Kyber reference source; FIPS 203 mapping | https://github.com/pq-crystals/kyber/tree/main/ref ; https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf |
| ML-DSA NTT/sampler material | pq-crystals Dilithium reference source; FIPS 204 mapping | https://github.com/pq-crystals/dilithium/tree/master/ref ; https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf |
| ML-KEM vectors | NIST ACVP-Server generated JSON corpus; exact imported commit/hash is not yet recorded | https://github.com/usnistgov/ACVP-Server |
| ML-DSA vectors | NIST ACVP-Server generated JSON corpus; exact imported commit/hash is not yet recorded | https://github.com/usnistgov/ACVP-Server |

No upstream license is inferred solely from a source URL or an algorithm
standard. The table is a provenance ledger and deliberately marks unresolved
license/revision facts rather than guessing.

## Runtime and build dependencies

These dependencies are not vendored by this repository. Their exact versions
are recorded in `toolchain.yaml` and `requirements/toolchain-versions.md`;
package hashes/lockfiles remain a remediation item.

| Dependency | Recorded role | Canonical URL |
| --- | --- | --- |
| MLIR-AIE / IRON | Native graph/toolchain provenance | https://github.com/Xilinx/mlir-aie |
| LLVM-AIE / Peano | AIE compiler provenance | https://github.com/Xilinx/llvm-aie |
| XRT | Native runtime provenance | https://github.com/Xilinx/XRT |
| kyber-py | Optional ML-KEM host oracle | https://github.com/GiacomoPope/kyber-py |
| dilithium-py | Optional ML-DSA host oracle | https://github.com/GiacomoPope/dilithium-py |
| NumPy | Host test/graph dependency | https://numpy.org/ |

## Research artifacts

`docs/pqc_dr2_evidence_20260818/` is a checksum-protected historical evidence
bundle, not a dependency distribution. Its contents may include captured
machine paths and diagnostic material. Do not alter it to “normalize” notices,
paths, or line endings; use a separate reviewed derivative for any public
redaction.
