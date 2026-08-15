# Documentation

Project documentation is organized separately from the repository landing page.

## Milestones and Mathematics

Read [M0–M17 Milestones and Mathematics](MILESTONES_AND_MATHEMATICS.md) for the native Windows platform overview, milestone map, DSP equations, finite-field and NTT mathematics, validated parameters, regression coverage, and correctness checklist. This covers the full v0.4.0 milestone set:

- **M0 – M15** — SDR pipeline (FIR, mixer, power, demod, 4-column parallel) and NTT lattice cryptography ([Barrett 1986](https://link.springer.com/chapter/10.1007/3-540-47721-7_24), radix-2 NTT butterflies, 16/256-point NTT/INTT, cyclic polynomial multiplication mod `q = 3329` per [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)).
- **M15b** — negacyclic polynomial multiplication in the Kyber / ML-KEM ring `Z_3329[x]/(x^256+1)` ([Kyber spec](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf); [Isabelle/AFP](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf); silicon-validated, bit-exact).
- **M32 (planned)** — [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM on top of M10–M15b. See [M32_FIPS203_MLKEM.md](M32_FIPS203_MLKEM.md). Not in the 16-suite.
- **M16** — CPU FFT/IFFT reference ([Cooley–Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf); [NumPy `fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html)).
- **M17** — Radix-4 [Stockham](https://dl.acm.org/doi/10.1145/1464182.1464209) FFT kernel on Phoenix NPU silicon, adapted from [FFT_R4_AIE](https://github.com/diacccc/FFT_R4_AIE).
- **M17-parallel (M17p)** — 4-column parallel FFT scaling of M17 ([Phoenix 4×5 XDNA1](https://docs.kernel.org/accel/amdxdna/amdnpu.html)) using the same ObjectFifo/`iron.Runtime` pattern as M9/M9b.
- **I/Q throughput demo** — `tests/npu_visible/` (not in the 16-suite). Measured 7.459 Msps / 29.84 MB/s I/Q in on a [10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) Phoenix NPU1.

## Related documents

- [ROADMAP.md](ROADMAP.md) — current status, milestone table, next-step planning, and toolchain events.
- [M32_FIPS203_MLKEM.md](M32_FIPS203_MLKEM.md) — planned FIPS 203 ML-KEM milestone (M32a–M32e gates).
- [CITATION_AUDIT.md](CITATION_AUDIT.md) — 2026-08-15 whole-repo citation pass.
- Root [Installation](../README.md#installation) — new-user path: clone, then `py .\install.py` (Xilinx XRT, Xilinx MLIR-AIE / IRON, LLVM Peano).
- [SETUP_WINDOWS.md](SETUP_WINDOWS.md) — longer native Windows walkthrough (XRT, mlir-aie, Peano, ironenv).
- [M2_TOOLCHAIN_PIN.md](M2_TOOLCHAIN_PIN.md) — reason for pinning mlir-aie at commit `3ca0193` (v1.4.1 + 13 commits, includes upstream PR #3545 `run_chain` fix required by parallel-DMA milestones).

## Validation boundary

The documentation distinguishes physical-NPU silicon validation from setup, hardware-dependent integration, and host-side reference work. `python run_all_silicon_tests.py` reports **16/16 PASS** on Phoenix NPU1: M3, M5–M15, M15b, M17, and M17p. A wipe-and-clone of `main` on 2026-08-15 reproduced that result in 95.91 s (cold xclbin compile) after `install.py`.
