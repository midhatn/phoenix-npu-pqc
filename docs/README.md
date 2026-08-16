# Documentation

Project documentation is organized separately from the repository landing page.

## Milestones and Mathematics

Read [M0–M33 Milestones and Mathematics](MILESTONES_AND_MATHEMATICS.md) for the native Windows platform overview, milestone map, DSP equations, finite-field and NTT mathematics, validated parameters, regression coverage, and correctness checklist. This covers the full v1.0.0 milestone set:

- **M0 – M15** — SDR pipeline (FIR, mixer, power, demod, 4-column parallel) and NTT lattice cryptography ([Barrett 1986](https://link.springer.com/chapter/10.1007/3-540-47721-7_24), radix-2 NTT butterflies, 16/256-point NTT/INTT, cyclic polynomial multiplication mod `q = 3329` per [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf)).
- **M15b** — negacyclic polynomial multiplication in the Kyber / ML-KEM ring `Z_3329[x]/(x^256+1)` ([Kyber spec](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf); [Isabelle/AFP](https://isa-afp.org/browser_info/current/AFP/CRYSTALS-Kyber/outline.pdf); silicon-validated, bit-exact).
- **M16** — CPU FFT/IFFT reference ([Cooley–Tukey 1965](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf); [NumPy `fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html)).
- **M17** — Radix-4 [Stockham](https://dl.acm.org/doi/10.1145/1464182.1464209) FFT kernel on Phoenix NPU silicon, adapted from [FFT_R4_AIE](https://github.com/diacccc/FFT_R4_AIE).
- **M17-parallel (M17p)** — 4-column parallel FFT scaling of M17 ([Phoenix 4×5 XDNA1](https://docs.kernel.org/accel/amdxdna/amdnpu.html)) using the same ObjectFifo/`iron.Runtime` pattern as M9/M9b.
- **M19 – M23** — filtering track: 8-tap complex FIR, fused polyphase decimator + interpolator, fused DDC, fused DUC, and M-path polyphase channelizer. Silicon-validated, bit-exact.
- **M24 – M27** — modulation and synchronization track: fused [Barker-13](https://en.wikipedia.org/wiki/Barker_code) matched-filter correlator, BPSK/QPSK receiver (Gardner TED + Costas), QAM-16 receiver with soft-decision LLR demapping, and OFDM loopback ([3GPP TS 38.211](https://www.3gpp.org/ftp/Specs/archive/38_series/38.211/38211-i50.zip), [IEEE 802.11-2020](https://ieeexplore.ieee.org/document/9363693), [Van de Beek 1995](https://ieeexplore.ieee.org/document/456405), [Edfors 1998](https://ieeexplore.ieee.org/document/725572)).
- **M32 (✅ v1.0.0)** — Post-Quantum Cryptography, [FIPS 203](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.203.pdf) ML-KEM. Sub-milestones M32b (NTT), M32c ([FIPS 202](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.202.pdf) Keccak / SHA-3 / SHAKE), M32d (K-PKE), M32e (ML-KEM.KeyGen / Encaps / Decaps composer, bit-exact vs [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server) KATs). Reference oracle: [`kyber-py` 1.0.1](https://github.com/GiacomoPope/kyber-py).
- **M33 (✅ v1.0.0)** — Post-Quantum Cryptography, [FIPS 204](https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.204.pdf) ML-DSA. Sub-milestones M33a (NTT over `Z_8380417`), M33b (rounding & hint), M33d (KeyGen composer, 75/75 vs KATs), M33e (Sign_internal + Verify_internal composer, 180/180 vs NIST ACVP-Server KATs). Reference oracle: [`dilithium-py` 1.4.0](https://github.com/GiacomoPope/dilithium-py). Full summary: [PQC_COMPLETE_V1.md](PQC_COMPLETE_V1.md).
- **I/Q throughput demo** — `tests/npu_visible/` (not in the 33-suite). Measured 7.459 Msps / 29.84 MB/s I/Q in on a [10 TOPS](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-9-7940hs.html) Phoenix NPU1.

## Related documents

- [ROADMAP.md](ROADMAP.md) — current status, milestone table, next-step planning, and toolchain events.
- [PQC_COMPLETE_V1.md](PQC_COMPLETE_V1.md) — v1.0.0 Post-Quantum Cryptography release summary (M32 ML-KEM + M33 ML-DSA closure).
- [M32_FIPS203_MLKEM.md](M32_FIPS203_MLKEM.md) — FIPS 203 ML-KEM milestone entry point (M32a–M32e gates, all ✅).
- [CITATION_AUDIT.md](CITATION_AUDIT.md) — 2026-08-15 whole-repo citation pass.
- Root [Installation](../README.md#installation) — new-user path: clone, then `py .\install.py` (Xilinx XRT, Xilinx MLIR-AIE / IRON, LLVM Peano).
- [SETUP_WINDOWS.md](SETUP_WINDOWS.md) — longer native Windows walkthrough (XRT, mlir-aie, Peano, ironenv).
- [M2_TOOLCHAIN_PIN.md](M2_TOOLCHAIN_PIN.md) — reason for pinning mlir-aie at commit `3ca0193` (v1.4.1 + 13 commits, includes upstream PR #3545 `run_chain` fix required by parallel-DMA milestones).

## Validation boundary

The documentation distinguishes physical-NPU silicon validation from setup, hardware-dependent integration, and host-side reference work. `python run_all_silicon_tests.py` reports **33/33 PASS** on Phoenix NPU1 at v1.0.0: M3, M5–M15, M15b, M17, M17p, M19–M27, and the Post-Quantum Cryptography track M32b/c/d/e + M33a/b/d/e. The M32 and M33 entries require the pinned PQC reference packages (`kyber-py`, `dilithium-py`, `pycryptodome`, `pyshake`) installed per [`SETUP_WINDOWS.md`](SETUP_WINDOWS.md#post-quantum-cryptography-reference-dependencies-m32--m33).
