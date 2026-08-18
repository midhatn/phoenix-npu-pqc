# Phoenix NPU PQC reproducibility guide

## Claim boundary

There are two deliberately separate execution paths:

1. `py .\run_all_silicon_tests.py` is the only canonical **silicon** runner.
   Its default action re-executes under the checkout-local IRON environment,
   preflights the native Windows toolchain and Phoenix NPU, then compiles and
   dispatches DR0, DR1, DR2a, DR2b, and DR2c in that exact order.
2. `python run_all_pqc_tests.py` is a **host preflight** only. It never loads
   MLIR-AIE, compiles an AIE program, or dispatches an NPU. A host pass cannot
   be called silicon validation.

No NPU result is accepted unless the canonical runner physically passes on the
target Phoenix laptop. The five gates are narrow device-resident milestones,
not complete ML-KEM, complete ML-DSA, or 100% algorithm residency. Integrated
ML-KEM-512 K-PKE.KeyGen (DR2d) is excluded from canonical dispatch and remains
`TOTAL 0/25 FAIL`, exit 1.

## Current and historical physical evidence

Keep these records separate:

| Record | Status | What it supports | What it does not support |
| --- | --- | --- | --- |
| Fresh 2026-08-18 sub-suite verification | DR0 24/24 + DR2a 13/13 + DR2b 13/13 + DR2c 11/11 = **61/61** | The four retained current-source native gates passed on the target Phoenix laptop. | A current five-gate 94/94 result; DR1 was not rerun in that fresh sub-suite. |
| External operator-retained historical DR1 log | Operator-supplied SHA-256 `85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E`; reported backend `dr1-mldsa44-expanda-rejntt:silicon`; reported `TOTAL 33/33 PASS` | Only the operator's historical assertion. The raw log is absent from this repository, so its bytes, hash, backend, and total are not independently reproducible here. | A current DR1 pass, a rerun against the current checkout, or a current canonical 94/94 result. |
| DR2d integrated KeyGen | `TOTAL 0/25 FAIL`, exit 1 | The integrated failure remains part of the evidence record. | DR2 closure, complete ML-KEM KeyGen, or a pass inferred from diagnostics/ELF/compile-only work. |

Do not add 61 and historical 33 to claim today's 94/94. Run the complete
canonical suite from the current checkout to establish that result.

## Native Windows installation and canonical run

On the target Windows 11 Phoenix laptop with CPython 3.13 x64:

```powershell
git clone https://github.com/midhatn/phoenix-npu-pqc.git
cd phoenix-npu-pqc
py .\install
```

The extensionless `install` launcher delegates to stdlib-only `install.py` and,
for a successful full install, automatically starts
`third_party\mlir-aie\ironenv\Scripts\python.exe run_all_silicon_tests.py`.
The installer provisions the pinned XRT SDK, exact `mlir-aie` commit, verified
`mlir_aie` CPython 3.13 wheel, official `iron_setup`, vendored `pyxrt`, and
Peano/llvm-aie. Direct XRT and wheel downloads are checked by exact byte length
and SHA-256 from `toolchain.yaml`.

The official `iron_setup.py` then resolves transitive Python dependencies from
package indexes. Those transitive dependencies are **not fully hash-locked** by
this repository; no claim that every installed package is locked is made.

The five canonical native gates do not require `kyber-py`, `dilithium-py`, or
`pytest`, so the physical installer does not download them from PyPI. They are
optional host/reference-oracle dependencies outside the canonical physical path;
an operator must separately pin and verify them when an optional workflow needs
them.

Run a new canonical validation and retain a local provenance record with:

```powershell
py .\run_all_silicon_tests.py --evidence-dir release-evidence\silicon
```

Each gate must exit 0, print its one exact silicon backend label, and print its
one exact total: DR0 24/24, DR1 33/33, DR2a 13/13, DR2b 13/13, and DR2c 11/11.
The runner fails closed on unavailable, skipped, reference, fallback,
diagnostic, generic-only, malformed, or wrong-total output. It fails fast and
never dispatches DR2d.

`--list` and `--preflight-only` do not compile or dispatch. They cannot support
a silicon claim. Maintenance modes `--check-only`, `--download-only`,
`--self-test`, and launcher option `--no-tests` also do not dispatch hardware.
The launcher treats `--no-tests` plus `--run-tests` as a mutually exclusive
argument error, so it cannot guess into a physical handoff.

## Host preflight and protected evidence

Use the host preflight only for source, contract, and reference coverage:

```powershell
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
```

The retained `validate_clean_clone.ps1` filename denotes a strict
**clean-checkout** host audit; it does not create a clone. It rejects staged,
unstaged, and untracked content before testing, records and reasserts the exact
`HEAD` commit, invokes the installer with `--no-tests`, and has no
hardware-dispatch switch:

```powershell
pwsh -File .\scripts\validate_clean_clone.ps1 -InstallHostDependencies
```

Never alter `docs/pqc_dr2_evidence_20260818/**` or either SHA-256 manifest.
Verify the protected bundle without regenerating its manifest:

```bash
(cd docs/pqc_dr2_evidence_20260818 && sha256sum -c SHA256SUMS)
```

## Toolchain and historical records

`toolchain.yaml` is the machine-readable source for the current native pins and
canonical gate contract. The dated DR1, DR2a, DR2b, DR2c, and DR2d records
remain historical evidence within their stated narrow scope. Cite the relevant
primary standards for cryptographic claims: [FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf),
[FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf), and
[FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf).
