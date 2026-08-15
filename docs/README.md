# Documentation

Project documentation is organized separately from the repository landing page.

## Milestones and Mathematics

Read [M0–M17 Milestones and Mathematics](MILESTONES_AND_MATHEMATICS.md) for the native Windows platform overview, milestone map, DSP equations, finite-field and NTT mathematics, validated parameters, regression coverage, and correctness checklist. This covers the full v0.4.0 milestone set:

- **M0 – M15** — SDR pipeline (FIR, mixer, power, demod, 4-column parallel) and NTT lattice cryptography (Barrett reduction, radix-2 NTT butterflies, 16/256-point NTT/INTT, cyclic polynomial multiplication mod q = 3329).
- **M15b** — parallel polynomial multiplication (`PORT_PENDING` on the iron API migration; see [ROADMAP.md](ROADMAP.md)).
- **M16** — CPU FFT/IFFT reference (mathematical ground truth for silicon FFT).
- **M17** — Radix-2 / Stockham FFT kernel on Phoenix NPU silicon.
- **M17-parallel (M17p)** — 4-column parallel FFT scaling of M17 using the same ObjectFifo/`iron.Runtime` pattern as M9/M9b.

## Related documents

- [ROADMAP.md](ROADMAP.md) — current status, milestone table, next-step planning, and the M15b iron API port plan.
- [SETUP_WINDOWS.md](SETUP_WINDOWS.md) — full native Windows install walkthrough (XRT, mlir-aie, Peano, ironenv).
- [M2_TOOLCHAIN_PIN.md](M2_TOOLCHAIN_PIN.md) — reason for pinning mlir-aie at commit `3ca0193` (v1.4.1 + 13 commits, includes upstream PR #3545 `run_chain` fix required by parallel-DMA milestones).

## Validation boundary

The documentation distinguishes physical-NPU silicon validation from setup, hardware-dependent integration, and host-side reference work. At v0.4.0, `python run_all_silicon_tests.py` reports **15/16 PASS** on Phoenix NPU1: M3 and M5–M17 pass on silicon, M17-parallel passes, and M15b is `PORT_PENDING` on the iron API migration.
