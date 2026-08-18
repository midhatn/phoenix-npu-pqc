# Phoenix NPU PQC — current Windows host-safe setup

## Scope and safety boundary

This is the current setup guide for **Phoenix NPU PQC**. It reproduces the
repository's host-safe contracts, reference checks, metadata validation, and
protected-evidence integrity checks. It does **not** authorize a physical NPU
run, native AIE compilation, cache lookup, or execution of any retained
PowerShell evidence script.

Historical native environment details are retained only as provenance in
[`toolchain.yaml`](../toolchain.yaml),
[`requirements/toolchain-versions.md`](../requirements/toolchain-versions.md),
and dated design/evidence records. Those records are not current execution
instructions and do not turn a host result into physical evidence.

## Clone the current repository

```powershell
Set-Location C:\
git clone https://github.com/midhatn/phoenix-npu-pqc.git
Set-Location C:\phoenix-npu-pqc
```

The retained import package is intentionally named `phoenix_sdr_dsp` for
compatibility; it is not the repository identity.

## Clean clone: one command

With the Windows Python launcher available, the complete default setup and
validation path is one command from the repository root:

```powershell
py .\install
```

The extensionless stdlib-only launcher requires **CPython 3.13 x64 on
Windows**, matching the repository's cp313 toolchain record. It checks
`numpy==2.5.2`; only if the dependency is absent or mismatched, it downloads
the exact `numpy-2.5.2-cp313-cp313-win_amd64.whl` to the ignored
`.bootstrap-cache/`, verifies its 12,460,532-byte length and SHA-256
`85aaccb24182c25df891ad0ec333585967e115269d5f1b17f2c9ae005bc96657`, then
installs that verified local file with `pip --no-index --no-deps`. The official
pin source is the [PyPI NumPy 2.5.2 JSON record](https://pypi.org/pypi/numpy/2.5.2/json);
the exact [wheel URL](https://files.pythonhosted.org/packages/15/20/f3489f86d81ea460b2bcdceaed094142ca6579f6be0ec527b781d39afe68/numpy-2.5.2-cp313-cp313-win_amd64.whl)
is hard-coded in `install`. It then verifies the installed import and
automatically invokes the root `run_all_silicon_tests.py` compatibility
forwarder.

Despite its historical name, `run_all_silicon_tests.py` forwards only to
`run_all_pqc_tests.py`, the explicit host-safe suite. Neither the launcher nor
either runner loads an NPU runtime, compiles an AIE program, probes a device,
or dispatches hardware. No administrator rights, XRT, IRON, Visual Studio, or
NPU are required.

For maintenance, use `py .\install --check-only` to inspect the exact
dependency without modifying it, `py .\install --no-tests` to provision and
verify without running tests, or `py .\install --self-test` to check the local
forwarder handoff without provisioning.
`py .\install.py` is retained solely as a compatibility shim; use the
extensionless command in all current instructions.

The default suite uses the standard-library `unittest` runner. It reports
whether optional `g++` C++ host-reference coverage is available. If `g++` is
not on `PATH`, only those native host-reference checks are skipped; Python and
contract coverage still pass. `g++` is optional and does not add any native
NPU tooling requirement. Historical M32/M33 composer utilities have separately
recorded dependencies in `requirements/toolchain-versions.md`; they are not
part of this path.

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
