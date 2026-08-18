# Phoenix NPU PQC reproducibility guide

## Purpose and safety boundary

This guide reproduces repository integrity and host-safe PQC validation. It
does not authorize a physical NPU run, compile a native graph, or claim that a
host result is silicon evidence. Native-only gate scripts remain retained
research material; physical evidence is interpreted through its dated records.

## Canonical sources

| Subject | Canonical source |
| --- | --- |
| Repository identity and current claim boundary | [Root README](../README.md) |
| History-preserving split and commits | [Repository split record](REPOSITORY_SPLIT_20260818.md) |
| DR status and stop rule | [Device-residency roadmap](PQC_DEVICE_RESIDENCY_ROADMAP.md) |
| DR2d negative result, chronology, and rejected paths | [DR2 expert escalation](PQC_DR2_EXPERT_ESCALATION_20260818.md) |
| Recovered DR2 lineage and local-source provenance | [DR2 local forensic recovery](PQC_DR2_LOCAL_FORENSIC_RECOVERY_20260818.md) |
| Byte-preserved DR2 forensic inventory | [`pqc_dr2_evidence_20260818/README.md`](pqc_dr2_evidence_20260818/README.md) and `SHA256SUMS` |
| M32/M33 mathematical and implementation boundaries | [M32 FIPS 203](M32_FIPS203_MLKEM.md), [M33a](M33a_DESIGN.md), [M33b](M33b_DESIGN.md), [M33d](M33d_DESIGN.md), and [M33e](M33e_DESIGN.md) |
| DR graph design boundaries | [DR0](PQC_DR0_DESIGN.md), [DR1](PQC_DR1_DESIGN.md), [DR2a](PQC_DR2A_DESIGN.md), [DR2b](PQC_DR2B_DESIGN.md), [DR2c](PQC_DR2C_DESIGN.md), and [DR2d](PQC_DR2D_DESIGN.md) |

## History anchors

- Historical M33e baseline tag `v1.0.0` resolves to
  `9c592a4c077c73f2ebf910aca0b6575664b0726f`.
- Native M33 runner lineage is
  `e77e7ed2783d88b5451394866d7ddfccd9db4f69`.
- DR0/DR1 graph lineage is
  `7b38973789fafb950a26551bc947f4fcaa91ec25`.
- DR2d's integrated physical record is `TOTAL 0/25 FAIL`, exit 1. This is the
  current integrated result; compile-only success and diagnostic captures do
  not supersede it.

## Toolchain record

The machine-readable pins are in [`../toolchain.yaml`](../toolchain.yaml).
The retained native environment was recorded with Windows 11, AMD Phoenix NPU1
(XDNA1/AIE2), XRT 2.21.0, MLIR-AIE `v1.4.1+13` at
`3ca0193cea9e2c39ec670a65f93e1dd43c969f22`, and LLVM-AIE / Peano
`21.0.0.2026080301+c9c5ecb7`. These are provenance pins, not a statement that
the current host-safe suite uses or validates an NPU.

First-party toolchain and standards references:

- [NIST FIPS 202](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.202.pdf)
- [NIST FIPS 203](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)
- [NIST FIPS 204](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.204.pdf)
- [AMD/Xilinx MLIR-AIE](https://github.com/Xilinx/mlir-aie)
- [AMD/Xilinx XRT](https://github.com/Xilinx/XRT)
- [AMD/Xilinx LLVM-AIE](https://github.com/Xilinx/llvm-aie)

## Known DR2 identity anchors

These identifiers locate retained research provenance; they do not establish
correctness or authorize a cache lookup, rebuild, or native execution.

| Item | Recorded identity |
| --- | --- |
| Integrated DR2d physical log | SHA-256 `1348dfb53446c4781c14b967fc535c5694cff2d1d56af097efc67cecd902be6c`; `TOTAL 0/25 FAIL`, exit 1 |
| Passed DR2b comparator | cache `4311961d4f3a43976aa5a60d`; core `0_3` ELF SHA-256 `0f1e4f9563a6716c3076bdc8ad4c8d43dc6dfd566cf0de2fd67b14d937261125` |
| W0 token-tap diagnostic | cache `320b9680889452b524538534`; raw 2,096-byte token SHA-256 `b7e75f7b55f8f3d30757ca5b0c3c9d13626b40e08cb5c6972681103395c20c53` |
| Retained production comparison cache | `04f147d54cb01d160974a6e6` |
| Sigma/PRF retry6 compile-only bundle | cache `337a8cdc94914d464c109ced`; MLIR SHA-256 `6f3cc8523e83e1bf99766795ed6d9fbc98f4d6dc17c3e918a66a65893dfc7d9c` |

The full protected source, graph, ABI, runner, patch, and retry-chain
identities are recorded in the [DR2 expert escalation](PQC_DR2_EXPERT_ESCALATION_20260818.md).

## Host-safe procedure

Run all commands from the repository root:

```bash
python run_all_pqc_tests.py --help
python run_all_pqc_tests.py --dry-run
python run_all_pqc_tests.py
python -m compileall -q phoenix_sdr_dsp tests run_all_pqc_tests.py run_all_silicon_tests.py
git diff --check
```

The test runner has an explicit allowlist of host-safe tests. It does not
select `*_silicon.py` files and does not call a native runner.

## Evidence integrity procedure

The DR2d evidence directory is protected by its manifest. Verify it without
altering its contents:

```bash
(cd docs/pqc_dr2_evidence_20260818 && sha256sum -c SHA256SUMS)
```

The manifest covers the recovered raw capture
`PQC_DR2D_W0_token_tap_tcId01_raw_20260818.bin` and the complete
`sigma_prf_retry_chain`. The repository attributes mark those captures
binary so line-ending conversion cannot silently change their bytes.

## Evidence interpretation

1. Treat physical logs and dated validation records as historical evidence
   within their stated scope.
2. Treat compile-only, ELF, placement, and source-level checks as build or
   diagnostic evidence, not as a physical exact-output result.
3. Treat DR2a/DR2b/DR2c as narrow results only; none is integrated K-PKE.KeyGen.
4. Treat the DR2d `0/25` result as unresolved until a new independently
   checked physical corpus and explicit decision record exist.
5. Do not infer complete ML-KEM, complete ML-DSA, FIPS conformance,
   constant-time behavior, side-channel resistance, zeroization, or
   certification from this repository.

## Research continuation questions

The active continuation question is the systematic semantic mismatch in the
integrated DR2d graph. The escalation and forensic-recovery records define the
observed mismatch boundary, cached DR2b comparisons, compile-only findings,
diagnostic captures, and rejected hypotheses. Any future investigation must
retain that provenance and distinguish a new physical corpus from host or
compile-only checks.
