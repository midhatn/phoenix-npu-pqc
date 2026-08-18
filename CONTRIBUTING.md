# Contributing to Phoenix NPU PQC

Phoenix NPU PQC is a research repository for FIPS 202/203/204 work on AMD
Phoenix NPU. Contributions must preserve evidence boundaries: a host check,
compile-only result, and physical exact-output result are different kinds of
evidence and must never be presented as interchangeable.

By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Security reports belong in [SECURITY.md](SECURITY.md), not public issues.

## Licensing of contributions

Unless a pull request clearly states otherwise and the maintainers accept that
exception in writing, contributions are submitted under the repository's
Apache License 2.0. By submitting a contribution, you represent that you have
the right and authority to license it on those terms.

Identify all third-party code, data, vectors, generated material, and adapted
algorithms in the pull request. Preserve applicable copyright and license
notices, provide the immutable upstream URL and revision when available, and
update [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Do not submit
employer-, university-, sponsor-, or collaborator-owned material without the
required authorization.

## Start with host-safe validation

The default test runner and CI do not use hardware:

```bash
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
python -m compileall -q phoenix_sdr_dsp tests run_all_pqc_tests.py run_all_silicon_tests.py
git diff --check
```

`run_all_silicon_tests.py` is the fail-closed physical NPU runner. Do not invoke
it during host-only validation. Its default path preflights the native Windows
toolchain and then dispatches the DR0, DR1, DR2a, DR2b, and DR2c milestone
gates on the Phoenix NPU.

Use the repository installer rather than installing an unpinned dependency by
hand:

```powershell
py .\install
```

The default install provisions the pinned native environment and then invokes
the physical runner. Use `py .\install --no-tests` when preparing a checkout
without authorizing physical dispatch.

## Working with PQC research material

1. Read the [documentation index](docs/README.md) and
   [reproducibility guide](docs/PQC_REPRODUCIBILITY.md).
2. For work touching DR2d, read
   [the expert escalation record](docs/PQC_DR2_EXPERT_ESCALATION_20260818.md)
   and preserve its `0/25` physical-result boundary.
3. Do not edit `docs/pqc_dr2_evidence_20260818/`, its `SHA256SUMS`, or other
   checksum-protected historical evidence. Verify it instead:

   ```bash
   (cd docs/pqc_dr2_evidence_20260818 && sha256sum -c SHA256SUMS)
   ```

4. Keep `phoenix_sdr_dsp` import paths working. The repository identity is
   Phoenix NPU PQC, while the import path is intentionally retained for
   compatibility.

## Native and physical work

Native MLIR-AIE / IRON / XRT changes require the pinned environment in
[`toolchain.yaml`](toolchain.yaml): MLIR-AIE `v1.4.1+13` at `3ca0193`,
LLVM-AIE / Peano `21.0.0.2026080301+c9c5ecb7`, and XRT 2.21.0. The
[Windows setup guide](docs/SETUP_WINDOWS.md) describes the retained
environment.

Do not add a hardware-dispatch command to CI or to the default runner. A
proposed physical experiment must state its scope, input corpus, independent
oracle, expected terminal output, fail-closed behavior, provenance capture,
and how it differs from existing evidence. Native execution is not implied or
authorized by opening an issue or pull request.

## Pull-request checklist

- [ ] The change is PQC-only and retains `phoenix_sdr_dsp` import compatibility.
- [ ] `python run_all_pqc_tests.py` passes.
- [ ] `git diff --check` passes.
- [ ] The relevant README, roadmap, design record, or reproducibility guide is updated.
- [ ] Historical evidence and checksums are unchanged, or a separately reviewed exact-byte restoration is documented.
- [ ] Claims distinguish host-safe, compile-only, and physical evidence.
- [ ] Toolchain metadata changed only with an accurately scoped provenance record.

## Reporting bugs and research failures

Use the PQC-focused issue forms for host-safe regressions, device-residency
research failures, or proposal discussion. Include exact commands, inputs,
toolchain versions, output, and the evidence class. The DR2d integrated
physical result remains unresolved; report a new result as a new record rather
than altering the existing evidence.
