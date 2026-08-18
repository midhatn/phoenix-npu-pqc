## Summary

Describe the PQC research, validation, provenance, or maintenance change and its claim boundary.

## Evidence class

- [ ] Host-safe contract or reference validation
- [ ] Compile-only or static analysis
- [ ] Historical evidence restoration or documentation
- [ ] Native evidence change with separately recorded provenance

## Validation

- [ ] `python run_all_pqc_tests.py` passes
- [ ] `python -m compileall -q phoenix_sdr_dsp tests run_all_pqc_tests.py run_all_silicon_tests.py` passes
- [ ] `git diff --check` passes
- [ ] `sha256sum -c SHA256SUMS` passes from `docs/pqc_dr2_evidence_20260818/`, or this PR accurately explains an existing gap

## Checklist

- [ ] The change is PQC-only and retains `phoenix_sdr_dsp` import compatibility.
- [ ] README, roadmap, design, reproducibility, or provenance documentation is updated where needed.
- [ ] I distinguish host-safe, compile-only, and physical evidence.
- [ ] I do not claim complete ML-KEM, complete ML-DSA, FIPS conformance, or 100% NPU residency without the required evidence.
- [ ] CI and default entrypoints remain host-only and do not dispatch hardware.
