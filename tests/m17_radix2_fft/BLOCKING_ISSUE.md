# M17 -- Blocking issue on mlir-aie 1.3.4 build

**Status:** Kernel does not compile. Root cause fully diagnosed.
**Date:** 2026-08-14
**Branch:** `feat/m17-radix2-fft-npu`

## Diagnosis

Reference kernel `fft64_kernel_v2.cc` attempts to use
`aie::detail::fft_dit_stage<Radix, Vectorization, Input, Output, Twiddle>::run(...)`
for a 6-stage radix-2 DIT FFT on cbfloat16. This fails at instantiation with:
error: implicit instantiation of undefined template
aie::detail::fft_dit<32, 0, 2, cbfloat16, cbfloat16, cbfloat16>

text

The compiler reports **all six stage instantiations** as undefined -- not just
Stage 4 (which is the known missing specialization for cbfloat16).

## Preprocessor probe

A `static_assert` diagnostic confirmed the underlying macro state on this build:

| Macro                                  | Value          |
|----------------------------------------|----------------|
| `__AIE_ARCH__`                         | 20 (AIE-ML / AIE2, matches Phoenix) |
| `__AIE_API_COMPLEX_VECTOR_SUPPORT__`   | 0 (undefined)  |
| `__AIE_API_CBF16_SUPPORT__`            | 0 (undefined)  |
| `__AIE_API_COMPLEX_FP32_EMULATION__`   | 0 (undefined)  |

## Impact

Because `__AIE_API_COMPLEX_VECTOR_SUPPORT__` is undefined, the entire radix-2
specialization file `aie_api/detail/aie2/fft_dit_radix2.hpp` is `#if`'d out at
line 10:

```cpp
#if __AIE_API_COMPLEX_VECTOR_SUPPORT__
// ...ALL radix-2 fft_dit<> specializations live here...
#endif
```

Result: `aie::detail::fft_dit<V, Stage, 2, Input, Output, Twiddle>` remains only
forward-declared (`detail/fft.hpp:355`). Every attempted instantiation of the
free function `aie::fft_dit_r2_stage<>()` or the class template
`aie::fft_dit<>` fails at instantiation time.

**This affects ALL data types, not just cbfloat16.** cint16 radix-2 would also
fail on this build.

## Build environment at time of diagnosis

- `mlir-aie == 1.3.4`
- `llvm-aie == 21.0.0.2026080301+c9c5ecb7`
- Target: AMD Ryzen 9 7940HS Phoenix (XDNA1, AIE-ML)
- Full pip freeze: `requirements_snapshot_pre_pathB.txt`

## Path forward being attempted (Path B)

Reinstall mlir-aie with a build that has FFT support enabled, i.e., a wheel
where `__AIE_API_COMPLEX_VECTOR_SUPPORT__ = 1` and `__AIE_API_CBF16_SUPPORT__ = 1`
for the AIE2 target.

If Path B fails, fallback is Path A: hand-coded radix-2 butterfly using
unconditionally-available AIE-ML vector primitives (`aie::vector`, `aie::mul`,
`aie::add`), bypassing the FFT-library-scope macros entirely.

## Files preserved in this commit

- `fft64_kernel_v2.cc` -- reference cbfloat16 radix-2 kernel (does NOT compile on current build)
- `test_fft_m17.py` -- host driver + M16 cross-check (5 test cases)
- `BLOCKING_ISSUE.md` -- this document
- `../../docs/M17_DESIGN.md` -- design doc
- `../../README_M17_INSTALL.md` -- install/run instructions
- `../../requirements_snapshot_pre_pathB.txt` -- pip freeze snapshot (repo root)

## References

Local header inspection during diagnosis:
- `aie_api/detail/fft.hpp:355` (forward decl of `fft_dit`)
- `aie_api/detail/aie2/fft_dit.hpp:19` (`fft_dit_stage<2, ...>::run` wrapper)
- `aie_api/detail/aie2/fft_dit_radix2.hpp:10,1069` (macro gate + cbfloat16 specializations)

Public source:
- github.com/Xilinx/aie_api  (fetched to cross-check the local header)