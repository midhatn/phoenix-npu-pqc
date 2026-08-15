# Citation audit — 2026-08-15

Whole-repo pass after the 16/16 silicon result. Goal: every technical claim
that could appear in a paper has a primary-source URL. Lab measurements
(17.46 s, SNRs, I/Q rates, seed-42 vectors) stay first-party — they are not
given invented citations.

## What changed

| File | Before | After | Notes |
|---|---:|---:|---|
| `docs/MILESTONES_AND_MATHEMATICS.md` | 1 | 82 | Biggest hole. Inline cites + full References. |
| `docs/ROADMAP.md` | 57 | 70 | Added FIPS 203, Kyber, Barrett, Stockham, Gentleman–Sande, Ozaki, Higham, IRON 1.4.1, FFT_R4_AIE. |
| `README.md` | 30 | 45 | Same academic set + kernel.org + IRON pin URLs. |
| `CITATION.cff` | 9 | 15 | Abstract flipped to 16/16. FFT_R4_AIE `repository-code` now [diacccc/FFT_R4_AIE](https://github.com/diacccc/FFT_R4_AIE). Added FIPS 203, Cooley–Tukey, Barrett, Stockham, Kyber. |
| `docs/M1_ARCHITECTURE_DECISION.md` | 2 | 4 | Pinned IRON guide to 1.4.1 (was unpinned `/dev/`). Outcome flipped 15/16 → 16/16. |
| `docs/M2_TOOLCHAIN_PIN.md` | 2 | 8 | PR #3545, `runtime.py` @ `3ca0193`, XRT 2.21.75, Python 3.13. |
| `docs/M17_V3_DESIGN.md` | 2 | 9 | Stockham, Cooley–Tukey, Ozaki, XAPP1406, Apache+LLVM, NumPy. |
| `docs/README.md` | 0 | 10 | Kyber, FIPS 203, Barrett, Stockham, FFT_R4_AIE, 10 TOPS. |
| `docs/SETUP_WINDOWS.md` | 2 | 15 | Official IRON 1.4.1, XRT zip, Python 3.13, PR #3545. |
| `CONTRIBUTING.md` | 0 | 6 | AMD 7940HS, kernel.org, mlir-aie v1.4.1, PR #3545, ruff. |
| `requirements/toolchain-versions.md` | 3 | 7 | 7940HS, kernel.org, XRT 2.21.75, IRON guide. |
| `tests/m16_fft_ref/README.md` | 5 | 8 | Higham DOI, Parseval, NumPy ifft. |
| `tests/npu_visible/README.md` | 2 | 4 | kernel.org 4×5 + Worker API pin. |
| `tests/m3_saxpy/README.md` | 0 | 4 | SAXPY / bfloat16 / IRON. |
| `tests/RENUMBERING.md` | 4 | 7 | FIPS 203, Kyber spec, Stockham, NumPy. |
| `SECURITY.md` | 4 | 5 | GitHub private-reporting docs. |
| `toolchain.yaml` | existing | +2 comments | kernel.org topology; XRT 2.21.75 tag. |
| `tests/m15b_negacyclic/test_negacyclic_m16.py` | 1 | 6 | FIPS 203, Kyber, Barrett, iron.Runtime. Schoolbook, not NTT. |

## Left uncited on purpose

| File | Why |
|---|---|
| `LICENSE` | SPDX Apache-2.0 text. |
| `CODE_OF_CONDUCT.md` | Already cites Contributor Covenant 2.1. |
| `dev-log.md` | Lab notebook. Measurements are first-party. |
| `.github/pull_request_template.md` | Process checklist. |
| Silicon numbers (17.46 s, 138.79 dB, 7.46 Msps, seed-42 vectors) | This laptop is the primary source. |

## Topology wording

[Linux `amdxdna`](https://docs.kernel.org/accel/amdxdna/amdnpu.html) describes Phoenix/Hawk Point as **4 rows of compute tiles arranged into 5 columns**. The repo README still says "4 Columns × 5 Rows". This audit cites kernel.org and does **not** rewrite the existing topology sentence.

## Barrett constants

- Method: [Barrett, CRYPTO 1986](https://link.springer.com/chapter/10.1007/3-540-47721-7_24).
- Textbook μ = floor(2^26 / 3329) = **20158** (M15).
- M15b kernel inherits **MU = 20165**. Do not unify.

## Preferred IRON docs pin

Use [mlir-aie 1.4.1 buildHostWinNative](https://xilinx.github.io/mlir-aie/1.4.1/buildHostWinNative/), not the unpinned `/dev/` tree.

## Not committed / not pushed

These files are local (and in the project file repo). Laptop `C:\phoenix-sdr-dsp` is still the source of truth. No GitHub commit, tag, or PR from this pass.
