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

## Host-safe prerequisites

Use a supported CPython interpreter and install the only dependency used by the
default host-safe suite:

```powershell
python -m pip install numpy
```

The default suite uses the standard-library `unittest` runner. Optional
historical M32/M33 composer utilities require separately pinned dependencies
recorded in `requirements/toolchain-versions.md`; they are not part of the
default validation gate.

## Validate the checkout

Run these commands from the repository root:

```powershell
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
python -m compileall -q phoenix_sdr_dsp tests tools install.py run_all_pqc_tests.py run_all_silicon_tests.py
```

`run_all_silicon_tests.py` is a compatibility alias that forwards to the same
host-safe suite. It does not load an NPU runtime, compile an AIE program, or
dispatch hardware.

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
