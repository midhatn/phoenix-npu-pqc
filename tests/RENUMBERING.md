# Test Directory Renumbering Audit — v0.2.1

This document records the one-time renumbering pass applied in v0.2.1 to resolve
a milestone-numbering collision between two schemes that had grown organically
in `tests/`.

## Background

Prior to v0.2.1, the `tests/` directory carried two overlapping M-numbering
schemes:

- **Scheme A** (canonical): matches the master prompt §16 milestone numbering
  and is the only scheme wired into the top-level `run_all_silicon_tests.py`
  regression runner. Covers M3, M5–M15 (SAXPY through polynomial multiplication).
- **Scheme B** (orphaned): four FFT/pipeline experiments that reused numbers
  already taken by Scheme A. Not present in the runner. Silicon-validated but
  independently.

The collision meant `tests/m10_benchmark/` and `tests/m10_modular/` both claimed
"M10", `tests/m11_fft/` and `tests/m11_butterfly/` both claimed "M11", etc.

## The renumbering

To align repository layout with the master prompt §16 canonical sequence,
Scheme B directories were renamed as follows in commit `<HASH>` (v0.2.1):

| Old path | New path | Justification |
|---|---|---|
| `tests/m10_benchmark/` | `tests/m9b_parallel_pipeline/` | Contents implement a 4-column parallel multi-stage demodulator pipeline — a companion to the M9 4-column parallel FIR, not a new milestone. Numbered as `m9b` (M9 extension). |
| `tests/m11_fft/` | `tests/m17_fft_dft/` | Contents implement a 64-point direct O(N²) DFT in `bfloat16`, silicon-validated against the NumPy DFT reference with `atol=0.1`. Per §16, NPU FFT is M17. Suffix `_dft` reflects the actual algorithm (direct DFT, not radix-2 butterfly). |
| `tests/m12_fft_parallel/` | `tests/m17p_fft_parallel/` | 4-column parallel variant of the M17 direct-DFT kernel. Suffix `p` denotes the parallel implementation. |
| `tests/m16_negacyclic/` | `tests/m15b_negacyclic/` | Contents test negacyclic polynomial multiplication in the ring `Z_q[x]/(x^N + 1)` — the Kyber ring per the [Isabelle/AFP CRYSTALS-Kyber formalization](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf). Canonically an extension of M15 (cyclic polynomial multiplication). Renamed to free the M16 slot for the CPU FFT reference (see §16). |

## Preservation of `git log --follow`

Each renamed file was moved by keeping its git blob SHA identical and only
changing the tree path. Git's copy/rename detection heuristic (`--follow`,
`--find-renames`) will recover the full pre-rename history for every file.

To trace a renamed file's full history:

```bash
git log --follow --stat tests/m17_fft_dft/fft64_kernel.cc
```

## What did NOT change

- **Scheme A directories** (`m5_fir` through `m15_polymul`) are untouched.
  They remain the canonical §16 M-numbering and are the only ones wired into
  `run_all_silicon_tests.py`.
- **Master prompt §16** was not modified. This pass moves the repository
  toward the prompt's canonical sequence, not the other way around.
- **Test contents** (source code, kernels, checkers) were not modified in
  this commit. Only the containing directory names changed.

## Follow-ups tracked in `docs/ROADMAP.md`

- ✅ **Done in v0.2.1** — Implement a proper M16 CPU FFT reference
  (radix-2 Cooley-Tukey). See `tests/m16_fft_ref/test_fft_reference_m16.py`,
  which cross-validates a recursive radix-2 FFT, an iterative bit-reversed
  radix-2 FFT, and a direct O(N²) DFT against NumPy across N ∈ {8, 16, 32,
  64, 128, 256, 512, 1024} with Parseval energy conservation exact to
  double-precision.
- ✅ **Done in v0.3.0** — Integrate the four renamed silicon tests
  (`m9b_parallel_pipeline`, `m15b_negacyclic`, `m17_fft_dft`,
  `m17p_fft_parallel`) into `run_all_silicon_tests.py`. Runner now dispatches
  16 milestones (from 12 in v0.2.0) and exits non-zero on any FAIL.
- **Open** — Ship an M17 radix-butterfly implementation to replace the direct
  O(N²) DFT with the O(N log N) [Cooley-Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf)
  algorithm. The M16 CPU iterative bit-reversed FFT is the reference dataflow;
  the M11 finite-field radix-2 butterfly is the silicon-proven arithmetic
  template.

## References

- Master prompt §16 milestone table:
  `/uploaded_attachments/…/Phoenix-SDR-DSP-Master-Prompt.md` (canonical
  M0–M31 sequence).
- Cooley, J. W. and Tukey, J. W. (1965). "An algorithm for the machine
  calculation of complex Fourier series." *Mathematics of Computation*
  19(90): 297–301. [Reprint](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf).
- Isabelle/AFP CRYSTALS-Kyber formalization outline (Kyber ring definition):
  https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf.
