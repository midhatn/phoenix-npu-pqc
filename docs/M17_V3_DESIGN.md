# M17 v3 — Radix-4 Stockham FFT on Peano (port of FFT_R4_AIE)

Status: **SHIPPED in v0.4.0** — silicon-verified on Phoenix NPU1 (forward FFT 138.79 dB SNR, IFFT round-trip 135.11 dB SNR; regression: `run_all_silicon_tests.py` at commit `1ec80c8`, 2026-08-15). Supersedes prior M17 v2 direction (aie_api `fft_dit_r2_stage<>` on cint16), which is deleted from the tree at this milestone.

## 1. Decision

**Port the AMD reference implementation [`diacccc/FFT_R4_AIE`](https://github.com/diacccc/FFT_R4_AIE) to our N=64 configuration** instead of hand-rolling a radix-2 kernel from scratch.

## 2. Why v3 changes course

M17 v2's approach was to compile `aie::fft_dit_r2_stage<>` on `cint16` under Peano. Over three probe iterations we established:

- `aie_api/detail/config.hpp` (Xilinx/aie_api submodule pinned by mlir-aie 1.4.1, SHA `bec000f...`) gates the complex-vector corridor on `__AIECC__`.
- **Peano defines `__AIECC__ = 1`** (verified via `clang++ --target=aie2p-none-unknown-elf -E -dM`, 2026-08-15). We had originally assumed `__AIECC__` was a Chess-only marker — it is not. llvm-aie/Peano also identifies itself as an AIE compiler by setting it.
- Therefore `__AIE_API_COMPLEX_VECTOR_SUPPORT__` = 0 under Peano, and the specialization for `fft_dit_stage<2, 64, cint16, cint16, cint16>` genuinely does not exist in the headers shipped with mlir-aie 1.4.1 for the Peano build.
- The corrected probe (with `__AIE_ARCH__=21` for aie2p) failed with the same "undefined template" error as prior probes — confirming the failure is not a flag misconfiguration but a genuine header gap.
- Peano additionally auto-sets `__AIE_ARCH__ = 21` and `__AIE_MODEL_VERSION__ = 11500` from `--target=aie2p-none-unknown-elf`, so no explicit `-D` overrides are needed for future work on this toolchain.

The cint16 corridor is closed under Peano in mlir-aie 1.4.1. Reopening it would require adding fft_dit_stage specializations ourselves, which defeats the purpose of using the aie_api abstraction. Even if reopened, the path is Q15 fixed-point twiddles → precision loss stacks up across stages.

The `diacccc/FFT_R4_AIE` reference implementation solves the problem more elegantly:

- **Complex f32 input/output** — matches our M11 direct-DFT interface exactly, no host-side changes required.
- **Zero use of `aie::fft_dit_*`** — the kernel does not touch aie_api's complex FFT primitives at all. It builds the entire butterfly out of `aie::mmul<4,8,8,bfloat16,bfloat16,accfloat>`, `aie::mac`, `aie::mul`, and `aie::filter_even/odd` — all real-vector primitives that we already know work on Peano. This is not a stylistic choice by the AMD authors — it is required, for the same reason our probes failed: the complex FFT specializations in `aie_api` are not available in Peano builds of mlir-aie 1.4.1.
- **AMD-authored, Apache-2.0 licensed** — copyright `Advanced Micro Devices, Inc. 2025-2026`, same author line as `mlir-aie` itself. We can adapt with attribution.
- **Radix-4 vs radix-2** — for N=64 that's 3 stages instead of 6, so cumulative bf16 error is roughly halved.
- **Validated at N=64** — the repo ships a full `fft_results_N64.csv` regression fixture, so somebody has already run this configuration end-to-end.

Reference materials mirrored under `references/fft_r4_aie/` (agent workspace):

| File | Size | Role |
|------|------|------|
| `kernels/fft_stockham_f32.cc` | 390 lines, 15 KB | The AIE kernel — the main asset |
| `single_core/single_core.py` | 239 lines | mlir-aie graph (old-style AIE dialect, not Runtime API) |
| `test.cpp` | 533 lines | XRT host driver, verifies against FFTW |
| `single_core/Makefile` | 51 lines | Build entry (`use_chess=0` selects Peano) |
| `makefile-common` | 216 lines | Peano/Chess flag machinery |
| `common.h` | 472 lines | Verification helpers |
| `fft_results_N64.csv` | 8.7 KB | N=64 regression fixture |

## 3. Algorithm — radix-4 DIT Stockham autosort

Schedule follows [Stockham, AFIPS 1966](https://dl.acm.org/doi/10.1145/1464182.1464209) (auto-sort, no bit-reversal). Complexity is the [Cooley–Tukey](https://garfield.library.upenn.edu/classics1993/A1993MJ84400001.pdf) O(N log N) bound. Implementation is the AMD [`FFT_R4_AIE`](https://github.com/diacccc/FFT_R4_AIE) kernel.

For N a power of 4, run `LOG4(N)` stages, `s` starts at 1 and multiplies by 4 each stage:

    a = x[q + s*(p + 0*m)]
    b = x[q + s*(p + 1*m)] * W_N^(q*m)
    c = x[q + s*(p + 2*m)] * W_N^(q*2*m)
    d = x[q + s*(p + 3*m)] * W_N^(q*3*m)

    y[q + s*(4*p + 0)] = a + b + c + d
    y[q + s*(4*p + 1)] = a - j*b - c + j*d
    y[q + s*(4*p + 2)] = a - b + c - d
    y[q + s*(4*p + 3)] = a + j*b - c - j*d

For N=64: 3 stages (`LOG4N = 3`), no bit-reversal needed (Stockham autosort produces naturally-ordered output).

## 4. Ozaki-style split-bf16 twiddles

Named after the [Ozaki–Ogita–Oishi–Rump error-free split](https://doi.org/10.1007/s11075-011-9478-1) (*Numerical Algorithms* 59:95–118, 2012). The AMD reference applies that idea to reconstruct an fp32 complex multiply from [`bfloat16`](https://docs.amd.com/r/en-US/xapp1406-aie-ml-fp-computation/Floating-Point-Numerical-Formats) slices accumulated in `accfloat`.

Each fp32 scalar is split into 4 bf16 slices; a complex twiddle W = W_re + j*W_im is stored as 8 bf16 values per twiddle: `[W_re_split0..3, W_im_split0..3]`. Per stage-`s` twiddle table, each `q` lane holds three twiddles (`W^m`, `W^2m`, `W^3m`) so a stage's twiddle block is `24 * s` bf16 elements.

The complex multiply is reconstructed as a sum of pairwise bf16 products of slices, using `aie::mac` accumulation into `accfloat` (fp32). The butterfly is expressed as an 8×8 real matvec (complex-expanded W4 matrix) and maps to `aie::mmul<4,8,8,bfloat16,bfloat16,accfloat>`.

Accumulator is fp32 throughout — we never round mid-stage. bf16 rounding is confined to the moments where an fp32 result is re-split into slices to feed the next mac chain.

## 5. Fixed knobs we must pin

| Knob | Value | Source |
|------|-------|--------|
| Device | `npu2` (aie2p / XDNA2) | `--dev npu2` |
| `dtype_in`, `dtype_out` | `f32`, `f32` | argparse defaults |
| `dtype_twiddle` | `bf16` (8 bf16 per complex twiddle) | fixed |
| MMUL shape | `<4, 8, 8>` on npu2 | `single_core.py` mac_dim_map, kernel lines 137, 306 |
| `AIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16` | **NOT set** — kernel uses `<4,8,8>` (non-emulated shape) | derived from mac_dim_map |
| Buffer allocation | `basic-sequential` (linear) | Makefile |
| Chess vs Peano | Peano (`use_chess=0`) | matches our M11/M17 v1 toolchain lock |

## 6. Compile flags — the Peano recipe

    KERNEL_CC = ${PEANO_INSTALL_DIR}/bin/clang++
    KERNEL_DEFINES = -DFFT_SIZE=64
    KERNEL_CFLAGS = -O2 -std=c++20 --target=aie2p-none-unknown-elf \
                    -Wno-parentheses -Wno-attributes -Wno-macro-redefined \
                    -Wno-empty-body -Wno-missing-template-arg-list-after-template-kw \
                    -DNDEBUG -I ${MLIR_AIE_DIR}/include \
                    -D__AIE_API_AIE_ADF_HPP__

Do NOT add `__AIE_ARCH__` or `__AIE_MODEL_VERSION__` — Peano sets these implicitly from `--target=aie2p-none-unknown-elf`. `__AIE_API_COMPLEX_VECTOR_SUPPORT__` is irrelevant since the kernel never touches complex vector types.

## 7. What we need to change vs. the reference

**Kernel side (`kernels/fft_stockham_f32.cc`):**
1. Verbatim copy of upstream with `-DFFT_SIZE=64` (kernel is already `constexpr`-parameterized).
2. Attribution comment block prepended.
3. No algorithmic changes in v3.

**Runtime side:**
Reference uses old-style `@core` / `@runtime_sequence` (AIE dialect direct). Our M11 host driver uses mlir-aie 1.4.1 Runtime API (`Program`, `Worker`, `Runtime`). We port the ObjectFifo topology (input signal, twiddle table, output signal → single compute tile) into the Runtime API form, matching M11's structure exactly. The twiddle table becomes a third XRT bo alongside input/output.

**Host driver side:**
- Reuse M11's structure: allocate three bo's (input, twiddle, output), fill twiddles from a Python helper that mirrors reference `test.cpp` twiddle generator, run, verify against [`numpy.fft.fft`](https://numpy.org/doc/stable/reference/generated/numpy.fft.fft.html).
- Twiddle table size for N=64 with LOG4N=3: sum over stages `s = 1, 4, 16` of `24 * s = 24 + 96 + 384 = 504 bf16` = **1008 bytes**.

## 8. Milestones and exit criteria

| Milestone | Deliverable | Exit criterion |
|-----------|-------------|----------------|
| **v3-a** | Kernel builds under Peano | ✅ **PASSED 2026-08-15**: `fft_stockham_f32.o` (10072 bytes, `.text.fft_stockham_f32` 7392 bytes), symbols `fft_stockham_f32` + `zero_f32` global, only undefined ref is `get_cycles`, no warnings |
| v3-b | mlir-aie graph builds | `aiecc.py` produces `final.xclbin` and `insts.bin` with no errors |
| v3-c | Host driver runs on silicon | XRT reports kernel completion, no faults |
| v3-d | Numerical correctness | Max abs error vs. `numpy.fft.fft` ≤ 1e-3 on random unit-scale input (radix-4 bf16 target) |
| v3-e | Regression cross-check | Bit-compatible with `fft_results_N64.csv` on the same input (soft goal) |
| v3-f | Merge and tag | Squash-merge to `main`, tag `v0.4.0-m17v3` |

## 9. Risks (post-v3-a status)

**R1: mlir-aie 1.4.1 vs. reference toolchain version.** RETIRED — kernel compiles cleanly against 1.4.1 headers.

**R2: `mmul<4,8,8,bfloat16,bfloat16,accfloat>` availability.** RETIRED — mmul instantiations resolved successfully in v3-a build; `.text.fft_stockham_f32` produced with no undefined mmul references.

**R3: Twiddle table generation.** OPEN — deferred to v3-c. Ozaki splitting is fiddly; unit-test the Python generator before running on hardware.

**R4: FFT_R4_AIE authenticity.** RETIRED — code compiles clean against upstream mlir-aie, license header matches mlir-aie project style, regression CSV present.

**R5: Radix-4 requires N = 4^k.** For N=64 = 4^3, exact. Not blocking for v3.

## 10. Explicitly deferred

- Any modifications to the ObjectFifo topology.
- Performance benchmarking against M11 direct-DFT.
- IFFT variant (add in v3.1).
- N != 64 (parameterize in v3.2).

## 11. Attribution

Reference: [diacccc/FFT_R4_AIE](https://github.com/diacccc/FFT_R4_AIE), commit `main` as of 2026-04-28.
License: [Apache-2.0 WITH LLVM-exception](https://spdx.org/licenses/Apache-2.0-with-LLVM-exception.html).
Copyright: (C) 2025-2026, Advanced Micro Devices, Inc.

All ported files in Phoenix-SDR-DSP that derive from this reference retain the SPDX header and add an "Adapted from …" note above our own copyright line.