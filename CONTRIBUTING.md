# Contributing to Phoenix SDR-DSP

Thanks for your interest in improving this project. This is a research-quality
NPU acceleration framework that runs directly on AMD Ryzen AI Phoenix silicon
(XDNA1 / AIE2), so contributions need to preserve the bit-accurate silicon
verification guarantees of the master regression suite.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Security issues should go through [SECURITY.md](SECURITY.md), not the public
issue tracker.

---

## 1. Prerequisites

You need an AMD Ryzen AI Phoenix or Hawk Point laptop (Ryzen 7040 or 8040
series with XDNA1 / AIE2 NPU) running Windows 11 Pro build 22H2 or newer.
The full toolchain is captured in [`toolchain.yaml`](toolchain.yaml):

| Component        | Verified version                     |
| ---------------- | ------------------------------------ |
| Windows          | 11 Pro 26200 (25H2)                  |
| AMD NPU driver   | 32.0.20102.3930                      |
| NPU firmware     | 1.5.5.391                            |
| XRT              | 2.21.0                               |
| Python           | 3.13.15                              |
| mlir-aie         | v1.4.1 + 13 commits (pin `3ca0193`)  |
| llvm-aie (Peano) | 21.0.0.2026080301+c9c5ecb7           |

The mlir-aie pin is v1.4.1 plus PR #3545 (run_chain executable-lifetime fix,
required by parallel-DMA milestones). See
[`docs/M2_TOOLCHAIN_PIN.md`](docs/M2_TOOLCHAIN_PIN.md) for details.

See [`docs/SETUP_WINDOWS.md`](docs/SETUP_WINDOWS.md) for the full install
walkthrough, or run the one-shot bootstrap:

```powershell
.\scripts\bootstrap_env.ps1
```

---

## 2. Development workflow

### Activate the environment

Every session starts by activating `ironenv`:

```powershell
& "C:\phoenix-sdr-dsp\third_party\mlir-aie\ironenv\Scripts\Activate.ps1"
```

### Verify silicon before touching anything

```powershell
python run_all_silicon_tests.py
```

You should see `15/16 PASS` in ~60 s (M15b is `PORT_PENDING` on the iron API
migration — see [`docs/ROADMAP.md`](docs/ROADMAP.md)). If not, fix your
environment before starting work. `scripts/verify_environment.ps1` runs quick
smoke checks.

### Make your change

Small, focused commits are strongly preferred. Follow existing style:

- Python: `ruff` (config is CI-driven — run `ruff check --fix .`)
- C++ AIE2 kernels (`*.cc`): match the vectorization style of adjacent files
- MLIR / eDSL: match the ObjectFifo IRON conventions used in `tests/m*_*/`

### Verify silicon AFTER your change

Re-run the full regression:

```powershell
python run_all_silicon_tests.py
```

Any milestone that regresses is a blocker. Paste the SUMMARY block into your
PR description.

---

## 3. Adding a new milestone

Follow the existing shape of a milestone directory (see `tests/m15_polymul/`):

tests/mN_your_name/
├── test_your_kernel_mN.py # IRON eDSL + XRT dispatch + host verify
├── your_kernel.cc # AIE2 vectorized kernel (if applicable)
└── README.md # numerical spec, expected pass criteria

1. Add a matching entry to `run_all_silicon_tests.py`.
2. Add the milestone to the `verification.last_verified.milestones` list in
   [`toolchain.yaml`](toolchain.yaml).
3. Update `README.md` "Validated Silicon Milestones" table.
4. Verify: full 15/16 PASS is preserved (or 16/16 if your milestone brings
   M15b back with the iron API port).

---

## 4. Pull request checklist

Copy this into the PR body:

- [ ] `ruff check .` passes
- [ ] `python run_all_silicon_tests.py` passes all pre-existing milestones
      bit-accurate; SUMMARY block pasted in this PR
- [ ] Any new milestone added to `toolchain.yaml` and README
- [ ] Docs updated (`README.md`, `docs/`) where behavior changed
- [ ] Toolchain versions in `toolchain.yaml` updated only if I actually
      upgraded a component AND the full regression passed on the new version
- [ ] Commit messages are descriptive

Then open the PR against `main`. CI will run lint + CFF/YAML validation +
M12 NTT CPU reference + M16 FFT CPU reference + Markdown link check. If your
change touches the mlir-aie/Peano install path, add the `run-onboarding-smoke`
label to the PR to also run the fork-onboarding smoke job.

---

## 5. Reporting bugs

The issue tracker has three forms tailored to this project — pick the most
specific:

- **Silicon regression / milestone failure** — a milestone stopped passing
  or produced incorrect numerical output on physical NPU hardware
- **Bug report** — build, install, script, or docs
- **Feature request** — new milestone, kernel, or infrastructure

For upstream bugs (kernel driver, mlir-aie, llvm-aie) the chooser links
directly to the correct upstream tracker.

---

## 6. Style — quick reference

- Python: 4-space indent, LF endings, UTF-8 without BOM. `ruff` will fix
  most things.
- PowerShell scripts (`*.ps1`): CRLF endings preserved (see
  `.gitattributes`).
- YAML: 2-space indent (see `.editorconfig`).
- Commit messages: imperative present, `scope: short summary`, then blank
  line, then bullet-pointed detail. Examples:
  - `feat(m17): add bit-reversed radix-4 NTT kernel`
  - `fix(m9): correct FIR tap indexing at column boundaries`
  - `chore(ci): pin ruff to 0.5.x`

Thanks for contributing.
