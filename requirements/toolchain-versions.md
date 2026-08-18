# Native Windows toolchain record

This is the current native-release toolchain record for Phoenix NPU PQC. The
machine-readable pins are in [`../toolchain.yaml`](../toolchain.yaml). The
canonical physical command is `py .\run_all_silicon_tests.py`; it is the only
runner whose result can be described as silicon validation.

## Target environment

| Component | Required or verified value |
| --- | --- |
| Host OS | Windows 11 22H2 or newer; verified 25H2 (26200) |
| Host Python | CPython 3.13 x64; verified 3.13.15 |
| Target | AMD Phoenix / Hawk Point NPU1, XDNA1 / AIE2 |
| Driver | Minimum and verified `32.0.20102.3930` |
| XRT SDK archive release | `2.21.75`, direct zip size and SHA-256 pinned in `toolchain.yaml` |
| XRT runtime-reported version | `2.21.0`; distinct from the pinned SDK archive release |
| MLIR-AIE source | `3ca0193cea9e2c39ec670a65f93e1dd43c969f22` |
| `mlir_aie` wheel | `1.4.1` CPython 3.13 `win_amd64`, direct size and SHA-256 pinned |
| LLVM-AIE / Peano | `21.0.0.2026080301+c9c5ecb7` |
| Environment | `third_party\mlir-aie\ironenv` |

The extensionless `py .\install` launcher delegates to `install.py`. A full
successful install runs official `iron_setup.py`, installs the vendored `pyxrt`
binding, verifies `aie`/IRON and Peano, and automatically invokes the
canonical runner under ironenv. `--check-only`, `--download-only`, `--self-test`,
and `--no-tests` never dispatch hardware.

## Integrity boundary

The installer verifies each directly downloaded XRT SDK and `mlir_aie` wheel by
exact byte length and SHA-256, and it pins the MLIR-AIE source commit. The
official `iron_setup.py` then resolves transitive Python dependencies from
package indexes. That transitive set is **not fully hash-locked** by this
repository. A complete independently verified wheelhouse would be required to
claim that every installed package is locked.

The default physical installer does not install `kyber-py`, `dilithium-py`, or
`pytest` from PyPI. They are not required by DR0, DR1, DR2a, DR2b, or DR2c and
are optional host/reference-oracle dependencies that need separate operator
pinning and verification.

## Canonical gate contract

The ordered native gates are DR0 24, DR1 33, DR2a 13, DR2b 13, and DR2c 11,
for 94 cases. Each accepted subprocess output contains exactly its expected
`Backend: <label>:silicon` line and one exact `TOTAL n/n PASS` line. DR2d is
not dispatched; its integrated physical status is `TOTAL 0/25 FAIL`, exit 1.
The five gates are narrow device-resident milestones, not complete ML-KEM,
complete ML-DSA, or 100% algorithm residency.

The user must not claim today's 94/94. The fresh 2026-08-18 current-source
sub-suite is DR0 + DR2a + DR2b + DR2c = 61/61. DR1 is an external,
operator-retained historical assertion: SHA-256
`85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E`,
reported backend `dr1-mldsa44-expanda-rejntt:silicon`, reported `TOTAL 33/33
PASS`. The raw log is absent from this checkout and is not independently
reproducible. A current canonical run on the target Phoenix laptop is required
for a current five-gate claim.
