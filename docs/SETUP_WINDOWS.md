# Phoenix NPU PQC — current Windows native setup

## Scope and safety boundary

This is the current setup guide for **Phoenix NPU PQC**. The repository identity
and its binding validation rule are NPU-native: canonical PQC validation must
physically compile and dispatch on an AMD Phoenix NPU. Host tests are a separate
preflight and can never satisfy or be labelled silicon validation.

Two paths are described below:

1. `py .\install` — provision the native toolchain and, on success, run the
   canonical physical runner `run_all_silicon_tests.py` on the target laptop.
2. `python run_all_pqc_tests.py` — the host preflight, which never loads the
   MLIR-AIE runtime, compiles an AIE program, probes a device, or dispatches
   hardware, and never produces silicon evidence.

Nothing here authorizes editing the protected DR2d evidence bundle or any
`SHA256SUMS` manifest, and nothing here authorizes a DR2d dispatch.

Historical native environment details are retained as provenance in
[`toolchain.yaml`](../toolchain.yaml),
[`requirements/toolchain-versions.md`](../requirements/toolchain-versions.md),
and dated design/evidence records. Those records are not a substitute for a
current canonical run.

## Clone the current repository

```powershell
Set-Location C:\
git clone https://github.com/midhatn/phoenix-npu-pqc.git
Set-Location C:\phoenix-npu-pqc
```

The retained import package is intentionally named `phoenix_sdr_dsp` for
compatibility; it is not the repository identity.

## Clean clone: one command

With the Windows Python launcher available, the complete native setup and
validation path is one command from the repository root:

```powershell
py .\install
```

`install` is the primary extensionless launcher. It is standard-library only, so
it runs on a stock **CPython 3.13 x64 on Windows** — matching the repository's
cp313 toolchain record — before any environment exists, and it delegates to the
maintained implementation in `install.py`. It performs, in order:

1. Fail-closed prerequisite checks: Windows 11 build floor, CPython 3.13 x64,
   Git, the AMD NPU driver minimum from `toolchain.yaml`, `xrt-smi` device
   enumeration, and Visual Studio native build tools.
2. Idempotent download of the pinned XRT Windows SDK zip, verified by exact byte
   length and SHA-256 from [`toolchain.yaml`](../toolchain.yaml), then atomic
   extraction after the cached archive and required `pyxrt.pyd` member are
   revalidated. The extraction marker is diagnostic metadata, not an integrity
   decision.
3. Idempotent download of the pinned `mlir_aie` CPython 3.13 `win_amd64` wheel
   into a local wheelhouse, verified by exact byte length and SHA-256.
4. A shallow `mlir-aie` checkout pinned to the exact verified commit.
5. The official
   [`iron_setup`](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/)
   native-Windows IRON environment in `third_party/mlir-aie/ironenv`, using the
   local wheelhouse for the pinned wheel.
6. Vendored `pyxrt` bindings plus `PEANO_INSTALL_DIR`, then a smoke check of
   `pyxrt`, `aie.iron`, and the Peano / `llvm-aie` `clang++`.
7. On success, automatic invocation of the canonical physical runner
   `run_all_silicon_tests.py` under that checkout `ironenv`.

`py .\install.py` remains supported as the legacy entry point.

### Integrity boundary

The XRT SDK zip and the `mlir_aie` wheel are downloaded directly and verified by
exact byte length and SHA-256, and `mlir-aie` is pinned to an exact commit. The
XRT direct-download archive release is `2.21.75`; the separately recorded
runtime-reported XRT value is `2.21.0`. These are distinct fields in
[`toolchain.yaml`](../toolchain.yaml), not competing archive pins.
official `iron_setup` step then resolves a further transitive Python dependency
set from package indexes, and that set is **not** fully hash-locked by this
repository. A fully hash-locked environment would require a complete,
independently produced verified wheelhouse. Do not describe this install as
fully locked.

The physical installer does not install `kyber-py`, `dilithium-py`, or `pytest`
from PyPI. The five canonical native gates do not require them. They remain
optional host/reference-oracle dependencies and require a separately pinned,
verified operator workflow when needed.

### Non-dispatching maintenance modes

- `py .\install --check-only` — prerequisite report only.
- `py .\install --download-only` — verified artifact provisioning only.
- `py .\install --self-test` — offline download/repair/hash-failure logic.
- `py .\install --no-tests` — full provisioning without the physical handoff.

None of these compiles an AIE program or dispatches hardware.
`--no-tests` and `--run-tests` are mutually exclusive; combining them fails
before the maintained installer is invoked.

## Canonical silicon validation

```powershell
py .\run_all_silicon_tests.py
```

This is the only runner whose output may be described as silicon validation. It
re-execs under the checkout `ironenv`, preflights the native toolchain and the
Phoenix NPU, then physically dispatches five ordered fail-closed gates:

| Order | Gate | Backend label | Cases |
| --- | --- | --- | --- |
| 1 | DR0 | `m33-dr0:silicon` | 24 |
| 2 | DR1 | `dr1-mldsa44-expanda-rejntt:silicon` | 33 |
| 3 | DR2a | `dr2a-mlkem512-samplentt:silicon` | 13 |
| 4 | DR2b | `dr2b-mlkem512-noise-ntt:silicon` | 13 |
| 5 | DR2c | `dr2c-mlkem512-keygen-row:silicon` | 11 |

A gate is accepted only on exit code 0 with its exact `Backend:` line and its
anchored `TOTAL n/n PASS` line for the exact expected case count, and with no
unavailable / skip / reference / fallback / diagnostic marker. The run fails fast
on the first failure. A full pass means **5 gates / 94 cases physically passed on
Phoenix NPU**; it is not complete ML-KEM or ML-DSA and not 100% algorithm
residency. DR2d is not dispatched.

Non-dispatching inspection: `--list` prints the ordered plan and exits;
`--preflight-only` probes the toolchain and device and exits before compilation.

No NPU claim is accepted unless canonical native runner output from the target
laptop passes. On 2026-08-18 the operator freshly verified retained
current-source hashes and exact gates DR0 24/24, DR2a 13/13, DR2b 13/13, and
DR2c 11/11: 61/61 in total. DR1 has a separately reported external,
operator-retained historical physical-log SHA-256
`85B373B1E3B8A1BD883DA6BBDE73F874EE5C331B4AE419E5D161758A64EB4A7E`,
reported as backend `dr1-mldsa44-expanda-rejntt:silicon` and `TOTAL 33/33
PASS`. Its raw bytes are absent from this repository, so the entry is not
independently reproducible here. Do not describe these separate records as a
current 94/94: rerun the complete canonical sequence on the target laptop. The
retained DR2a/DR2b/DR2c logs are narrow evidence for those gates only.

To retain a timestamped local record from a new canonical run without changing
the protected DR2d evidence tree:

```powershell
py .\run_all_silicon_tests.py --evidence-dir release-evidence\silicon
```

The record includes checkout provenance, preflight status, and merged output
for each gate. It does not turn an unavailable, skipped, reference, fallback,
generic-only, or failed result into a pass.

## Host preflight

```powershell
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
```

`run_all_pqc_tests.py` is an explicit host preflight. It never selects a
`*_silicon.py` gate, loads an NPU runtime, compiles an AIE program, probes a
device, or dispatches hardware. No administrator rights, XRT, IRON, Visual
Studio, or NPU are required. A pass is a host preflight pass only and is never
silicon evidence.

The preflight uses the standard-library `unittest` runner and reports whether
optional `g++` C++ host-reference coverage is available. If `g++` is not on
`PATH`, only those native host-reference checks are skipped; Python and contract
coverage still pass. `g++` is optional and adds no native NPU tooling
requirement. Historical M32/M33 composer utilities have separately recorded
dependencies in `requirements/toolchain-versions.md`; they are not part of this
path.

## Verify protected evidence without modifying it

The DR2d forensic bundle is immutable research evidence. Verify it, but do not
edit its contents or its manifest:

```powershell
Set-Location docs\pqc_dr2_evidence_20260818
sha256sum -c SHA256SUMS
Set-Location ..\..
```

If a Windows environment has no `sha256sum`, use a trusted equivalent only to
compare the existing SHA-256 values; do not regenerate or replace
`SHA256SUMS`.

## Native and physical research

Physical work requires separately recorded authorization, exact source/artifact
provenance, an independent oracle, and a new evidence record. The current
repository result for integrated DR2d ML-KEM-512 K-PKE.KeyGen is
`TOTAL 0/25 FAIL`, exit 1. Compile-only output, host checks, and diagnostics do
not supersede that result. Read the
[reproducibility guide](PQC_REPRODUCIBILITY.md) and
[DR2 expert escalation](PQC_DR2_EXPERT_ESCALATION_20260818.md) before
interpreting retained native material.

## References

- NIST FIPS 202, SHA-3 Standard: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf
- NIST FIPS 203, ML-KEM: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf
- NIST FIPS 204, ML-DSA: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf
- AMD NPU Linux kernel documentation (Phoenix/Hawk Point topology): https://docs.kernel.org/accel/amdxdna/amdnpu.html
